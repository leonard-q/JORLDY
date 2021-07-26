import torch
torch.backends.cudnn.benchmark = True
import torch.nn.functional as F
import numpy as np
import copy

from core.network import Network
from core.optimizer import Optimizer
from .utils import PERMultistepBuffer
from .dqn import DQNAgent

class ApeXAgent(DQNAgent):
    def __init__(self,
                 # ApeX
                 epsilon = 0.4,
                 epsilon_alpha = 0.7,                 
                 clip_grad_norm = 40.0,
                 # PER
                 alpha = 0.6,
                 beta = 0.4,
                 learn_period = 4,
                 uniform_sample_prob = 1e-3,
                 # MultiStep
                 n_step = 4,
                 **kwargs
                 ):
        super(ApeXAgent, self).__init__(**kwargs)
        # ApeX
        self.epsilon = epsilon
        self.epsilon_alpha = epsilon_alpha
        self.clip_grad_norm = clip_grad_norm
        
        # PER
        self.alpha = alpha
        self.beta = beta
        self.learn_period = learn_period
        self.learn_period_stamp = 0 
        self.uniform_sample_prob = uniform_sample_prob
        self.beta_add = 1/self.explore_step
        
        # MultiStep
        self.n_step = n_step
        self.memory = PERMultistepBuffer(self.buffer_size, self.n_step, self.uniform_sample_prob)
        
    def learn(self):
        transitions, weights, indices, sampled_p, mean_p = self.memory.sample(self.beta, self.batch_size)
        state, action, reward, next_state, done = map(lambda x: torch.as_tensor(x, dtype=torch.float32, device=self.device), transitions)
        
        eye = torch.eye(self.action_size).to(self.device)
        one_hot_action = eye[action[:, 0].view(-1).long()]
        q = (self.network(state) * one_hot_action).sum(1, keepdims=True)
        
        with torch.no_grad():
            max_Q = torch.max(q).item()
            next_q = self.network(next_state)
            max_a = torch.argmax(next_q, axis=1)
            max_eye = torch.eye(self.action_size).to(self.device)
            max_one_hot_action = eye[max_a.view(-1).long()]
            
            next_target_q = self.target_network(next_state)
            target_q = (next_target_q * max_one_hot_action).sum(1, keepdims=True)
            
            for i in reversed(range(self.n_step)):
                target_q = reward[:, i] + (1 - done[:, i]) * self.gamma * target_q
            
        # Update sum tree
        td_error = abs(target_q - q)
        p_j = torch.pow(td_error, self.alpha)
        for i, p in zip(indices, p_j):
            self.memory.update_priority(p.item(), i)
                
        # Annealing beta
        self.beta = min(1.0, self.beta + self.beta_add)
        
        weights = torch.unsqueeze(torch.FloatTensor(weights).to(self.device), -1)
                
        loss = (weights * (td_error**2)).mean()        
        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.network.parameters(), self.clip_grad_norm)
        
        self.optimizer.step()
        
        self.num_learn += 1

        result = {
            "loss" : loss.item(),
            "max_Q": max_Q,
            "sampled_p": sampled_p,
            "mean_p": mean_p,
        }

        return result
    
    def process(self, transitions, step):
        result = {}
        
        # Process per step
        delta_t = step - self.time_t
        self.memory.store(transitions, delta_t)
        self.time_t = step
        self.target_update_stamp += delta_t
        self.learn_period_stamp += delta_t
        
        if (self.learn_period_stamp > self.learn_period and
            self.memory.buffer_counter > self.batch_size and
            self.time_t >= self.start_train_step):
            result = self.learn()
            self.learn_period_stamp = 0

        # Process per step if train start
        if self.num_learn > 0 and self.target_update_stamp > self.target_update_period:
            self.update_target()
            self.target_update_stamp = 0
            
        return result

    def set_distributed(self, id, num_worker):
        self.epsilon = self.epsilon**(1 + (id/(num_worker-1))*self.epsilon_alpha)
        return self