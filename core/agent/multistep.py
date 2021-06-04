import torch
torch.backends.cudnn.benchmark = True
import torch.nn.functional as F

from .utils import MultistepBuffer
from .dqn import DQNAgent

class MultistepDQNAgent(DQNAgent):
    def __init__(self, n_step = 5, **kwargs):
        super(MultistepDQNAgent, self).__init__(**kwargs)
        self.n_step = n_step
        self.memory = MultistepBuffer(self.buffer_size, self.n_step)
    
    def learn(self):
#         shapes of 1-step implementations: (batch_size, dimension_data)
#         shapes of multistep implementations: (batch_size, steps, dimension_data)

        transitions = self.memory.sample(self.batch_size)
        state, action, reward, next_state, done = map(lambda x: torch.FloatTensor(x).to(self.device), transitions)
        eye = torch.eye(self.action_size).to(self.device)
        one_hot_action = eye[action[:, 0].view(-1).long()]
        q = (self.network(state) * one_hot_action).sum(1, keepdims=True)
        with torch.no_grad():
            max_Q = torch.max(q).item()
            next_q = self.target_network(next_state)
            target_q = next_q.max(1, keepdims=True).values

            for i in reversed(range(self.n_step)):
                target_q = reward[:, i] + (1 - done[:, i]) * self.gamma * target_q
            
        loss = F.smooth_l1_loss(q, target_q)

        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        self.optimizer.step()
        
        self.num_learn += 1

        result = {
            "loss" : loss.item(),
            "epsilon" : self.epsilon,
            "max_Q": max_Q,
        }
        
        return result
    
    def process(self, transitions, step):
        result = {}

        # Process per step
        delta_t = step - self.time_t
        self.memory.store(transitions, delta_t)
        self.time_t = step
        self.target_update_stamp += delta_t
        
        if self.memory.size > self.batch_size and self.time_t >= self.start_train_step:
            result = self.learn()

        # Process per step if train start
        if self.num_learn > 0:
            self.epsilon_decay(delta_t)

            if self.target_update_stamp > self.target_update_period:
                self.update_target()
                self.target_update_stamp = 0

        return result