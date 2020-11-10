### DQN CratPole Config ###

env = {
    "name":"cartpole",
    "mode":"discrete",
}

agent = {
    "name": "dqn",
    "network": "dqn",
    "optimizer": "adam",
    "learning_rate": 1e-4,
    "gamma": 0.99,
    "epsilon_init": 1.0,
    "epsilon_min": 0.1,
    "explore_step": 20000,
    "buffer_size": 10000,
    "batch_size": 32,
    "start_train_step": 10000,
    "target_update_term": 200,
}

train = {
    "training" : True,
    "load_path" : None,
    "train_step" : 80000,
    "test_step" : 10000,
    "print_term" : 5,
    "save_term" : 1000,
}