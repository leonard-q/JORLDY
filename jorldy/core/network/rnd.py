import torch
import torch.nn.functional as F

from .utils import RewardForwardFilter, RunningMeanStd
# normalize observation
# assumed state shape: (batch_size, dim_state)
def normalize_obs(obs, m, v):    
    return torch.clip((obs - m) / (torch.sqrt(v)+1e-7), min=-5., max=5.)

class RND_MLP(torch.nn.Module):
    def __init__(self, D_in, D_out, num_workers, gamma_i, 
                 ri_normalize=True, obs_normalize=True, batch_norm=True, D_hidden=256):
        super(RND_MLP, self).__init__()
        self.D_in = D_in
        self.D_out = D_out
        self.num_workers = num_workers
        self.rms_obs = RunningMeanStd(D_in)
        self.rms_ri = RunningMeanStd(1)
        self.rff = RewardForwardFilter(gamma_i, num_workers)
        self.obs_normalize = obs_normalize
        self.ri_normalize = ri_normalize
        self.batch_norm = batch_norm
        
        feature_size = 256
        
        self.fc1_predict = torch.nn.Linear(self.D_in, D_hidden)
        self.fc2_predict = torch.nn.Linear(D_hidden, feature_size)
            
        self.fc1_target = torch.nn.Linear(self.D_in, D_hidden)
        self.fc2_target = torch.nn.Linear(D_hidden, feature_size)

        if batch_norm:
            self.bn1_predict = torch.nn.BatchNorm1d(D_hidden)
            self.bn2_predict = torch.nn.BatchNorm1d(feature_size)
            
            self.bn1_target = torch.nn.BatchNorm1d(D_hidden)
            self.bn2_target = torch.nn.BatchNorm1d(feature_size)
        
    def update_rms_obs(self, v):
        self.rms_obs.update(v)
        
    def update_rms_ri(self, v):
        self.rms_ri.update(v)
                            
    def forward(self, s_next, update_ri=False):
        if self.obs_normalize: s_next = normalize_obs(s_next, self.rms_obs.mean, self.rms_obs.var)
        
        if self.batch_norm:
            p = F.relu(self.bn1_predict(self.fc1_predict(s_next)))
            p = F.relu(self.bn2_predict(self.fc2_predict(p)))
            
            t = F.relu(self.bn1_target(self.fc1_target(s_next)))
            t = F.relu(self.bn2_target(self.fc2_target(t)))
        else:
            p = F.relu(self.fc1_predict(s_next))
            p = F.relu(self.fc2_predict(p))
            
            t = F.relu(self.fc1_target(s_next))
            t = F.relu(self.fc2_target(t))
        
        r_i = torch.mean(torch.square(p - t), axis = 1)
        
        if update_ri:
            ri_T = r_i.view(self.num_workers, -1).T # (n_batch, n_workers)
            rewems = torch.stack([self.rff.update(rit.detach()) for rit in ri_T]).ravel() # (n_batch, n_workers) -> (n_batch * n_workers)
            self.update_rms_ri(rewems)
        if self.ri_normalize: r_i = r_i / (torch.sqrt(self.rms_ri.var) + 1e-7)
        
        return r_i
        
class RND_CNN(torch.nn.Module):
    def __init__(self, D_in, D_out, num_workers, gamma_i, 
                 ri_normalize=True, obs_normalize=True, batch_norm=True, D_hidden=512):
        super(RND_CNN, self).__init__()
        self.D_in = D_in
        self.D_out = D_out
        self.num_workers = num_workers
        self.rms_obs = RunningMeanStd(D_in)
        self.rms_ri = RunningMeanStd(1)
        self.rff = RewardForwardFilter(gamma_i, num_workers)
        self.obs_normalize = obs_normalize
        self.ri_normalize = ri_normalize
        self.batch_norm = batch_norm

        dim1 = ((self.D_in[1] - 8)//4 + 1, (self.D_in[2] - 8)//4 + 1)
        dim2 = ((dim1[0] - 4)//2 + 1, (dim1[1] - 4)//2 + 1)
        dim3 = ((dim2[0] - 3)//1 + 1, (dim2[1] - 3)//1 + 1)
        
        feature_size = 64*dim3[0]*dim3[1]
        
        # Predictor Networks
        self.conv1_predict = torch.nn.Conv2d(in_channels=self.D_in[0], out_channels=32, kernel_size=8, stride=4)
        self.conv2_predict = torch.nn.Conv2d(in_channels=32, out_channels=64, kernel_size=4, stride=2)
        self.conv3_predict = torch.nn.Conv2d(in_channels=64, out_channels=64, kernel_size=3, stride=1)

        self.fc1_predict = torch.nn.Linear(feature_size, D_hidden)
        self.fc2_predict = torch.nn.Linear(D_hidden, D_hidden)
        self.fc3_predict = torch.nn.Linear(D_hidden, D_hidden)
        
        # Target Networks
        self.conv1_target = torch.nn.Conv2d(in_channels=self.D_in[0], out_channels=32, kernel_size=8, stride=4)
        self.conv2_target = torch.nn.Conv2d(in_channels=32, out_channels=64, kernel_size=4, stride=2)
        self.conv3_target = torch.nn.Conv2d(in_channels=64, out_channels=64, kernel_size=3, stride=1)

        self.fc1_target = torch.nn.Linear(feature_size, D_hidden)
                
        if batch_norm:
            self.bn1_predict = torch.nn.BatchNorm2d(32)
            self.bn2_predict = torch.nn.BatchNorm2d(64)
            self.bn3_predict = torch.nn.BatchNorm2d(64)
                        
            self.bn1_target = torch.nn.BatchNorm2d(32)
            self.bn2_target = torch.nn.BatchNorm2d(64)
            self.bn3_target = torch.nn.BatchNorm2d(64)
            
    def update_rms_obs(self, v):
        self.rms_obs.update(v/255.0)
        
    def update_rms_ri(self, v):
        self.rms_ri.update(v)
        
    def forward(self, s_next, update_ri=False):
        s_next = s_next/255.0
        if self.obs_normalize: s_next = normalize_obs(s_next, self.rms_obs.mean, self.rms_obs.var)
                
        if self.batch_norm:
            p = F.relu(self.bn1_predict(self.conv1_predict(s_next)))
            p = F.relu(self.bn2_predict(self.conv2_predict(p)))
            p = F.relu(self.bn3_predict(self.conv3_predict(p)))
        else:
            p = F.relu(self.conv1_predict(s_next)) 
            p = F.relu(self.conv2_predict(p)) 
            p = F.relu(self.conv3_predict(p)) 
            
        p = p.view(p.size(0), -1)
        p = F.relu(self.fc1_predict(p))
        p = F.relu(self.fc2_predict(p))
        p = self.fc3_predict(p)
        
        if self.batch_norm:
            t = F.relu(self.bn1_target(self.conv1_target(s_next)))
            t = F.relu(self.bn2_target(self.conv2_target(t)))
            t = F.relu(self.bn3_target(self.conv3_target(t)))
        else:
            t = F.relu(self.conv1_target(s_next)) 
            t = F.relu(self.conv2_target(t)) 
            t = F.relu(self.conv3_target(t)) 
            
        t = t.view(t.size(0), -1)
        t = self.fc1_target(t)
        
        r_i = torch.mean(torch.square(p - t), axis = 1)
        
        if update_ri:
            ri_T = r_i.view(self.num_workers, -1).T # (n_batch, n_workers)
            rewems = torch.stack([self.rff.update(rit.detach()) for rit in ri_T]).ravel() # (n_batch, n_workers) -> (n_batch * n_workers)
            self.update_rms_ri(rewems)
        if self.ri_normalize: r_i = r_i / (torch.sqrt(self.rms_ri.var) + 1e-7)
        
        return r_i