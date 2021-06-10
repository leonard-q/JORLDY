import os
import ray
import numpy as np 
import copy
from collections import defaultdict
from functools import reduce
import datetime, time
from collections import defaultdict, deque

# gifManager
import cv2, imageio
from PIL import Image
import shutil

from torch.utils.tensorboard import SummaryWriter

class MetricManager:
    def __init__(self):
        self.metrics = defaultdict(list)
        
    def append(self, result):
        for key, value in result.items():
            self.metrics[key].append(value)
    
    def get_statistics(self, mode='mean'):
        ret = dict()
        if mode == 'mean':
            for key, value in self.metrics.items():
                ret[key] = 0 if len(value) == 0 else round(sum(value)/len(value), 4)
                self.metrics[key].clear()
        return ret
    
class LogManager:
    def __init__(self, env, id, purpose=None):
        self.id=id
        now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.path = f"./logs/{env}/{id}/{now}/" if purpose is None else f"./logs/{env}/{purpose}/{id}/{now}/"
        self.writer = SummaryWriter(self.path)
        self.stamp = time.time()
        
    def write_scalar(self, scalar_dict, step):
        for key, value in scalar_dict.items():
            self.writer.add_scalar(f"{self.id}/"+key, value, step)
            self.writer.add_scalar("all/"+key, value, step)
            if "score" in key:
                time_delta = int(time.time() - self.stamp)
                self.writer.add_scalar(f"{self.id}/{key}_per_time", value, time_delta)
                self.writer.add_scalar(f"all/{key}_per_time", value, time_delta)

class TimeManager:
    def __init__(self, n_mean = 20):
        self.n_mean = n_mean
        self.reset()
    
    def reset(self):
        self.timedic = dict()
    
    def start(self, keyword):
        if keyword not in self.timedic:
            self.timedic[keyword] = {
                'start_timestamp': time.time(),
                'deque': deque(maxlen=self.n_mean),
                'mean': -1,
                'last_time': -1,
            }
        else:
            self.timedic[keyword]['start_timestamp'] = time.time()
    
    def end(self, keyword):
        if keyword in self.timedic:
            time_current = time.time() - self.timedic[keyword]['start_timestamp']
            self.timedic[keyword]['last_time'] = time_current
            self.timedic[keyword]['deque'].append(time_current)
            self.timedic[keyword]['start_timestamp'] = -1
            self.timedic[keyword]['mean'] = sum(self.timedic[keyword]['deque']) / len(self.timedic[keyword]['deque'])
            
            return self.timedic[keyword]['last_time'], self.timedic[keyword]['mean']
        
    def get_statistics(self):
        return {k: self.timedic[k]['mean'] for k in self.timedic}
        
            
class TestManager:
    def __init__(self, env, iteration=10):
        assert iteration > 0
        self.env = env
        self.iteration = iteration
    
    def test(self, agent):
        scores = []
        for i in range(self.iteration):
            done = False
            state = self.env.reset()
            while not done:
                action = agent.act(state, training=False)
                state, reward, done = self.env.step(action)
            scores.append(self.env.score)
            
        return np.mean(scores)

class DistributedManager:
    def __init__(self, Env, env_config, Agent, agent_config, num_worker):
        ray.init()
        agent = Agent(**agent_config)
        Env, env_config, agent = map(ray.put, [Env, env_config, agent])
        self.actors = [Actor.remote(Env, env_config, agent, i) for i in range(num_worker)]

    def run(self, step=1):
        assert step > 0
        transitions = reduce(lambda x,y: x+y, 
                             ray.get([actor.run.remote(step) for actor in self.actors]))
        return transitions

    def sync(self, sync_item):
        sync_item = ray.put(sync_item)
        ray.get([actor.sync.remote(sync_item) for actor in self.actors])
        
    def terminate(self):
        ray.shutdown()

class GIFManager:
    def __init__(self, env):
        self.env = env
        self.now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        
    def make_gif(self, agent, step, algo_name, env_name):
        gif_path = './gif/' + env_name + '/' + algo_name + '/' + self.now + '/'
        
        os.makedirs("./images4gif", exist_ok=True)
        os.makedirs(gif_path, exist_ok=True)
        
        count = 0
        
        done = False
#         state = self.env.reset_raw()
        state = self.env.reset()
        
        state_frame = state[:,-1,:,:]
        state_frame = np.reshape(state_frame, (state_frame.shape[1], state_frame.shape[2], 1))
        
        count_str = str(count).zfill(4)
        cv2.imwrite('./images4gif/'+count_str+'.jpg', state_frame)
        
        while not done:
            action = agent.act(state, training=False) #하 state.... 
            state, reward, done = self.env.step(np.array([1]))
#             state, reward, done = self.env.step_raw(action)
            
            count += 1
            
            state_frame = state[:,-1,:,:]
            state_frame = np.reshape(state_frame, (state_frame.shape[1], state_frame.shape[2], 1))

            count_str = str(count).zfill(4)
            cv2.imwrite('./images4gif/'+count_str+'.jpg', state_frame)

        # Make gif 
        path = [f"./images4gif/{i}" for i in os.listdir("./images4gif")]
        paths = [Image.open(i) for i in path]
        
        imageio.mimsave(gif_path + str(step)+'.gif', paths, fps=20)
        
        print("=================== gif file is saved at {} ===================".format(gif_path))
        shutil.rmtree("./images4gif")
        
@ray.remote
class Actor:
    def __init__(self, Env, env_config, agent, id):
        self.env = Env(id=id+1, **env_config)
        self.agent = agent.set_distributed(id)
        self.state = self.env.reset()
    
    def run(self, step):
        transitions = []
        for t in range(step):
            action = self.agent.act(self.state, training=True)
            next_state, reward, done = self.env.step(action)
            transitions.append((self.state, action, reward, next_state, done))
            self.state = next_state if not done else self.env.reset()
        return transitions
    
    def sync(self, sync_item):
        self.agent.sync_in(**sync_item)

