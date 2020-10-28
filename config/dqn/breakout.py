### DQN BreakOut Config ###

env = {
    "name": "breakout",
    "gray_img": True,
    "img_width": 84,
    "img_height": 84,
    "stack_frame": 4,
}

agent = {
    "name": "dqn",
    "network": "dqn_cnn",
    "optimizer": "adam",
    "learning_rate": 0.00025,
    "gamma": 0.99,
    "epsilon_init": 1.0,
    "epsilon_min": 0.1,
    "explore_step": 2000000,
    "buffer_size": 500000,
    "batch_size": 32,
    "start_train_step": 100000,
    "target_update_term": 1000,
}

train = {
    "training" : True,
    "load_path" : None, #"./logs/breakout/dqn/20201027142347/",
    "train_step" : 10000000,
    "test_step" : 1000000,
    "print_term" : 50,
    "save_term" : 1000,
}