import os
import ray
import numpy as np 
import copy
from collections import defaultdict
from functools import reduce
import datetime, time
from collections import defaultdict, deque
import imageio

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
        
    def write(self, scalar_dict, frames, step):
        for key, value in scalar_dict.items():
            self.writer.add_scalar(f"{self.id}/"+key, value, step)
            self.writer.add_scalar("all/"+key, value, step)
            if "score" in key:
                time_delta = int(time.time() - self.stamp)
                self.writer.add_scalar(f"{self.id}/{key}_per_time", value, time_delta)
                self.writer.add_scalar(f"all/{key}_per_time", value, time_delta)
        
        if len(frames) > 0 :
            write_path = os.path.join(self.path, f"{step}.gif")
            imageio.mimwrite(write_path, frames, fps=60)
            print(f"...Record episode to {write_path}...")

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
    def __init__(self, env, iteration=10, record=False, record_period=1000000):
        assert iteration > 0
        self.env = env
        self.iteration = iteration
        self.record = record and env.recordable()
        self.record_period = record_period
        self.record_stamp = 0
        self.time_t = 0
    
    def test(self, agent, step):
        scores = []
        frames = []
        self.record_stamp += step - self.time_t
        self.time_t = step
        record = self.record and self.record_stamp >= self.record_period
        for i in range(self.iteration):
            done = False
            state = self.env.reset()
            while not done:
                # record first iteration
                if record and i == 0: 
                    frames.append(self.env.get_frame())
                action = agent.act(state, training=False)
#                 state, reward, done = self.env.step(action)
                if self.env.mode ==  'discrete':
                    state, reward, done = self.env.step(action[:, :1].astype(np.long))
                elif self.env.mode == 'continuous':
                    state, reward, done = self.env.step(action[:, :self.action_size])
            scores.append(self.env.score)
            
        if record:
            self.record_stamp = 0
        return np.mean(scores), frames

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

@ray.remote
class Actor:
    def __init__(self, Env, env_config, agent, id):
        self.env = Env(id=id+1, **env_config)
        self.env_config = env_config
        self.agent = agent.set_distributed(id)
        self.state = self.env.reset()
        try:
            self.action_size = self.env.action_size
        except:
            self.action_size = self.env.action_space.n
            
    
    def run(self, step):
        transitions = []
        for t in range(step):
            action = self.agent.act(self.state, training=True)
            
            if self.env.mode ==  'discrete':
                next_state, reward, done = self.env.step(action[:, :1].astype(np.long))
            elif self.env.mode == 'continuous':
                next_state, reward, done = self.env.step(action[:, :self.action_size])
                
            transitions.append((self.state, action, reward, next_state, done))
            self.state = next_state if not done else self.env.reset()
        return transitions
    
    def sync(self, sync_item):
        self.agent.sync_in(**sync_item)