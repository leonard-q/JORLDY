import torch
torch.backends.cudnn.benchmark = True
import torch.nn.functional as F
from torch.distributions import Normal
import os 
import numpy as np

from core.network import Network
from core.optimizer import Optimizer
from core.buffer import ReplayBuffer
from .base import BaseAgent

# OU noise class 
class OU_noise:
    def __init__(self, action_size, mu, theta, sigma):
        self.action_size = action_size
        
        self.mu = mu
        self.theta = theta
        self.sigma = sigma
        
        self.reset()

    def reset(self):
        self.X = np.ones((1, self.action_size), dtype=np.float32) * self.mu

    def sample(self):
        dx = self.theta * (self.mu - self.X) + self.sigma * np.random.randn(len(self.X))
        self.X = self.X + dx
        return self.X
    
class DDPG(BaseAgent):
    def __init__(self,
                 state_size,
                 action_size,
                 actor= "ddpg_actor",
                 critic= "ddpg_critic",
                 head = None,
                 optim_config = {'actor':'adam','critic':'adam',
                                'actor_lr':5e-4,'critic_lr':1e-3},
                 gamma= 0.99,
                 buffer_size= 50000,
                 batch_size= 128,
                 start_train_step= 2000,
                 tau= 1e-3,
                 # OU noise
                 mu= 0,
                 theta= 1e-3,
                 sigma= 2e-3,
                 device=None,
                 **kwargs,
                 ):
        self.device = torch.device(device) if device else torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        self.actor = Network(actor, state_size, action_size, head=head).to(self.device)
        self.critic = Network(critic, state_size, action_size, head=head).to(self.device)
        self.target_actor = Network(actor, state_size, action_size, head=head).to(self.device)
        self.target_actor.load_state_dict(self.actor.state_dict())
        self.target_critic = Network(critic, state_size, action_size, head=head).to(self.device)
        self.target_critic.load_state_dict(self.critic.state_dict())
        
        self.actor_optimizer = Optimizer(optim_config.actor, self.actor.parameters(), lr=optim_config.actor_lr)
        self.critic_optimizer = Optimizer(optim_config.critic, self.critic.parameters(), lr=optim_config.critic_lr)
        
        self.OU = OU_noise(action_size, mu, theta, sigma)
        
        self.gamma = gamma
        self.tau = tau
        self.memory = ReplayBuffer(buffer_size)
        self.batch_size = batch_size
        self.start_train_step = start_train_step
        self.num_learn = 0

    @torch.no_grad()
    def act(self, state, training=True):
        self.actor.train(training)
        mu = self.actor(torch.as_tensor(state, dtype=torch.float32, device=self.device))
        mu = mu.cpu().numpy()
        action = mu + self.OU.sample() if training else mu
        return {'action': action}

    def learn(self):
        transitions = self.memory.sample(self.batch_size)
        for key in transitions.keys():
            transitions[key] = torch.as_tensor(transitions[key], dtype=torch.float32, device=self.device)

        state = transitions['state']
        action = transitions['action']
        reward = transitions['reward']
        next_state = transitions['next_state']
        done = transitions['done']
        
        # Critic Update
        with torch.no_grad():
            next_actions = self.target_actor(next_state)
            next_q = self.target_critic(next_state, next_actions)
            target_q = reward + (1 - done) * self.gamma * next_q
        q = self.critic(state, action)
        critic_loss = F.mse_loss(target_q, q)
        
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        self.critic_optimizer.step()
        
        max_Q = torch.max(target_q, axis=0).values.cpu().numpy()[0]
        
        # Actor Update
        action_pred = self.actor(state)
        actor_loss = -self.critic(state, action_pred).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()
        
        self.num_learn += 1
        
        result = {
            'critic_loss' : critic_loss.item(),
            'actor_loss' : actor_loss.item(),
            'max_Q' : max_Q,
        }
        return result

    def update_target_soft(self):
        for t_p, p in zip(self.target_critic.parameters(), self.critic.parameters()):
            t_p.data.copy_(self.tau*p.data + (1-self.tau)*t_p.data)
    
    def process(self, transitions, step):
        result = {}
        # Process per step
        self.memory.store(transitions)
        
        if self.memory.size > self.batch_size and step >= self.start_train_step:
            result = self.learn()
        if self.num_learn > 0:
            self.update_target_soft()

        return result

    def save(self, path):
        print(f"...Save model to {path}...")
        save_dict = {
            "actor" : self.actor.state_dict(),
            "actor_optimizer" : self.actor_optimizer.state_dict(),
            "critic" : self.critic.state_dict(),
            "critic_optimizer" : self.critic_optimizer.state_dict(),
        }
        torch.save(save_dict, os.path.join(path,"ckpt"))

    def load(self, path):
        print(f"...Load model from {path}...")
        checkpoint = torch.load(os.path.join(path,"ckpt"),map_location=self.device)
        self.actor.load_state_dict(checkpoint["actor"])
        self.actor_optimizer.load_state_dict(checkpoint["actor_optimizer"])

        self.critic.load_state_dict(checkpoint["critic"])
        self.target_critic.load_state_dict(self.critic.state_dict())
        self.critic_optimizer.load_state_dict(checkpoint["critic_optimizer"])
            
    def sync_in(self, weights):
        self.actor.load_state_dict(weights)
    
    def sync_out(self, device="cpu"):
        weights = self.actor.state_dict()
        for k, v in weights.items():
            weights[k] = v.to(device) 
        sync_item ={
            "weights": weights,
        }
        return sync_item