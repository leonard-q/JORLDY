import torch
import torch.nn.functional as F

class ContinuousPiV(torch.nn.Module):
    def __init__(self, D_in, D_out, D_hidden=512):
        super(ContinuousPiV, self).__init__()
        self.D_in = D_in
        self.D_out = D_out
        
        self.l1 = torch.nn.Linear(D_in, D_hidden)
        self.l2 = torch.nn.Linear(D_hidden, D_hidden)
        self.mu = torch.nn.Linear(D_hidden, D_out)
        self.log_std = torch.nn.Linear(D_hidden, D_out)
        self.Q = torch.nn.Linear(D_hidden+D_out, 1)

    def forward(self, x):
        x = F.relu(self.l1(x))
        x = F.relu(self.l2(x))
        
        mu = torch.clamp(self.mu(x), min=-8., max=8.)
        log_std = self.log_std(x)
        log_std = torch.clamp(log_std, min=-5., max=2.)
        return mu, log_std.exp()
    
    def calculate_Q(self, x, a):
        x = F.relu(self.l1(x))
        x = F.relu(self.l2(x))
        
        return self.Q(torch.cat([x, a], axis=-1))
    
    
class DiscretePiV(torch.nn.Module):
    def __init__(self, D_in, D_out, D_hidden=512):
        super(DiscretePiV, self).__init__()
        self.D_in = D_in
        self.D_out = D_out
        
        self.l1 = torch.nn.Linear(D_in, D_hidden)
        self.l2 = torch.nn.Linear(D_hidden, D_hidden)
        self.pi = torch.nn.Linear(D_hidden, D_out)
        self.Q = torch.nn.Linear(D_hidden, D_out)
        
    def forward(self, x):
        x = F.relu(self.l1(x))
        x = F.relu(self.l2(x))
        return F.softmax(self.pi(x), dim=-1), self.Q(x)
    
    
class ContinuousPiV_CNN(torch.nn.Module):
    def __init__(self, D_in, D_out, D_hidden=512):
        super(ContinuousPiV_CNN, self).__init__()
        self.D_in = D_in
        self.D_out = D_out
        
        self.conv1 = torch.nn.Conv2d(in_channels=D_in[0], out_channels=32, kernel_size=8, stride=4)
        dim1 = ((D_in[1] - 8)//4 + 1, (D_in[2] - 8)//4 + 1)
        self.conv2 = torch.nn.Conv2d(in_channels=32, out_channels=64, kernel_size=4, stride=2)
        dim2 = ((dim1[0] - 4)//2 + 1, (dim1[1] - 4)//2 + 1)
        self.conv3 = torch.nn.Conv2d(in_channels=64, out_channels=64, kernel_size=3, stride=1)
        dim3 = ((dim2[0] - 3)//1 + 1, (dim2[1] - 3)//1 + 1)
        
        self.fc1 = torch.nn.Linear(64*dim3[0]*dim3[1], D_hidden)
        self.mu = torch.nn.Linear(D_hidden, D_out)
        self.log_std = torch.nn.Linear(D_hidden, D_out)
        self.Q = torch.nn.Linear(D_hidden+D_out, 1)

    def forward(self, x):
        x = (x-(255.0/2))/(255.0/2)
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        x = F.relu(self.conv3(x))
        x = x.view(x.size(0), -1)
        
        x = F.relu(self.fc1(x))
        
        log_std = self.log_std(x)
        log_std = torch.clamp(log_std, min=-5., max=2.)
        return self.mu(x), log_std.exp(), self.v(x) #TODO: v->Q????
    
    
class DiscretePiV_CNN(torch.nn.Module):
    def __init__(self, D_in, D_out, D_hidden=512):
        super(DiscretePiV_CNN, self).__init__()
        self.D_in = D_in
        self.D_out = D_out
        
        self.conv1 = torch.nn.Conv2d(in_channels=D_in[0], out_channels=32, kernel_size=8, stride=4)
        dim1 = ((D_in[1] - 8)//4 + 1, (D_in[2] - 8)//4 + 1)
        self.conv2 = torch.nn.Conv2d(in_channels=32, out_channels=64, kernel_size=4, stride=2)
        dim2 = ((dim1[0] - 4)//2 + 1, (dim1[1] - 4)//2 + 1)
        self.conv3 = torch.nn.Conv2d(in_channels=64, out_channels=64, kernel_size=3, stride=1)
        dim3 = ((dim2[0] - 3)//1 + 1, (dim2[1] - 3)//1 + 1)
        
        self.fc1 = torch.nn.Linear(64*dim3[0]*dim3[1], D_hidden)
        
        self.pi = torch.nn.Linear(D_hidden, D_out)
        self.Q = torch.nn.Linear(D_hidden, D_out)
        
    def forward(self, x):
        x = (x-(255.0/2))/(255.0/2)
        x = F.relu(self.conv1(x))
        x = F.relu(self.conv2(x))
        x = F.relu(self.conv3(x))
        x = x.view(x.size(0), -1)
        
        x = F.relu(self.fc1(x))
        
        return F.softmax(self.pi(x), dim=-1), self.Q(x)