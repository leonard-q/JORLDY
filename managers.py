import numpy as np 
import datetime

from torch.utils.tensorboard import SummaryWriter

class MetricManager:
    def __init__(self):
        self.metrics = dict()
        
    def append(self, result):
        for key, value in result.items():
            if not key in self.metrics:
                self.metrics[key] = []
            self.metrics[key].append(value)
    
    def get_statistics(self, mode='mean'):
        ret = dict()
        if mode == 'mean':
            for key, value in self.metrics.items():
                ret[key] = 0 if len(value) == 0 else round(sum(value)/len(value), 4)
                self.metrics[key].clear()
        return ret
    
class LogManager:
    def __init__(self, env, agent):
        now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.path = f"./logs/{env}/{agent}/{now}/"
        self.writer = SummaryWriter(self.path)
        
    def write_scalar(self, scalar_dict, step):
        for key, value in scalar_dict.items():
            self.writer.add_scalar(key, value, step)    