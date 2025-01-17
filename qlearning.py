import sys
import numpy as np
import math
import random
import time as tm
import requests
import gym
import gym_maze

# Define the ESP32's IP address and port
ESP32_IP_ADDRESS = "192.168.222.8"
ESP32_PORT = 80

# Function to send direction to ESP32
def send_direction_to_esp32(direction):
    try:
        # Construct the URL for the ESP32
        url = f"http://{ESP32_IP_ADDRESS}:{ESP32_PORT}/direction"
        # Send the direction as a POST request
        response = requests.post(url, data={'dir': direction})
        if response.status_code == 200:
            print(f"Direction {direction} sent successfully")
        else:
            print(f"Failed to send direction {direction}: {response.status_code}")
    except Exception as e:
        print(f"Error sending direction {direction}: {e}")

env = gym.make("maze-sample-5x5-v0")
MAZE_SIZE = tuple((env.observation_space.high + np.ones(env.observation_space.shape)).astype(int))
NUM_BUCKETS = MAZE_SIZE  # one bucket per grid
MIN_EXPLORE_RATE = 0.001
MIN_LEARNING_RATE = 0.2
DECAY_FACTOR = np.prod(MAZE_SIZE, dtype=float) / 10.0
NUM_ACTIONS = env.action_space.n
STATE_BOUNDS = list(zip(env.observation_space.low, env.observation_space.high))

# Learning parameters
NUM_EPISODES = 500000
MAX_T = 1000
SOLVED_T = 100
STREAK_TO_END = 100
Q = np.zeros(NUM_BUCKETS + (NUM_ACTIONS,), dtype=float)

def select_action(state, explore_rate):
    # Select a random action
    if random.random() < explore_rate:
        action = env.action_space.sample()
    # Select the action with the highest q
    else:
        action = int(np.argmax(Q[state]))
    return action

def get_explore_rate(t):
    return max(MIN_EXPLORE_RATE, min(0.8, 1.0 - math.log10((t + 1) / DECAY_FACTOR)))

def get_learning_rate(t):
    return max(MIN_LEARNING_RATE, min(0.8, 1.0 - math.log10((t + 1) / DECAY_FACTOR)))

def state_to_bucket(state):
    bucket_indice = []
    for i in range(len(state)):
        if state[i] <= STATE_BOUNDS[i][0]:
            bucket_index = 0
        elif state[i] >= STATE_BOUNDS[i][1]:
            bucket_index = NUM_BUCKETS[i] - 1
        else:
            # Mapping the state bounds to the bucket array
            bound_width = STATE_BOUNDS[i][1] - STATE_BOUNDS[i][0]
            offset = (NUM_BUCKETS[i] - 1) * STATE_BOUNDS[i][0] / bound_width
            scaling = (NUM_BUCKETS[i] - 1) / bound_width
            bucket_index = int(round(scaling * state[i] - offset))
        bucket_indice.append(bucket_index)
    return tuple(bucket_indice)

def train():
    learning_rate = get_learning_rate(0)
    explore_rate = get_explore_rate(0)
    discount_factor = 0.99

    num_streaks = 0
    env.render()

    for episode in range(NUM_EPISODES):
        obv = env.reset()
        s = state_to_bucket(obv)
        total_reward = 0

        for t in range(MAX_T):
            a = select_action(s, explore_rate)
            obv, r1, d, _ = env.step(a)
            s1 = state_to_bucket(obv)
            total_reward += r1

            best_q = np.amax(Q[s1])
            Q[s + (a,)] += learning_rate * (r1 + discount_factor * (best_q) - Q[s + (a,)])
            s = s1

            env.render()

            if env.is_game_over():
                sys.exit()

            if d:
                print("Episode %d finished after %f time steps with total reward = %f (streak %d)."
                      % (episode, t, total_reward, num_streaks))

                if t <= SOLVED_T:
                    num_streaks += 1
                else:
                    num_streaks = 0
                break

            elif t >= MAX_T - 1:
                print("Episode %d timed out at %d with total reward = %f."
                      % (episode, t, total_reward))

            if num_streaks > STREAK_TO_END:
                break

            explore_rate = get_explore_rate(episode)
            learning_rate = get_learning_rate(episode)

        if num_streaks > STREAK_TO_END:
            break

def simulate():
    obv = env.reset()
    s = state_to_bucket(obv)
    d = False
    reward = 0
    time = 0
    env.render()
    tm.sleep(2)

    action_map = {
        0: 'F',  # Forward
        1: 'R',  # Right
        2: 'L',  # Backward
        3: 'B'   # Left
    }

    # Track the agent's orientation
    orientations = ['N', 'E', 'S', 'W']
    current_orientation = 0  # Start facing North

    previous_direction = None
    continuous_forward = False

    while not d:
        action = int(np.argmax(Q[s]))
        obv, r1, d, _ = env.step(action)
        env.render()
        tm.sleep(2)

        direction = action_map[action]

        # Determine if the action is a change in direction
        if previous_direction is None or (direction != 'F' and direction != previous_direction):
            print(f"Step {time}: {direction} ({s})")
            send_direction_to_esp32(direction)
            previous_direction = direction
            continuous_forward = False
        else:
            if direction == 'F' and not continuous_forward:
                print(f"Step {time}: F ({s})")
                send_direction_to_esp32('F')
                continuous_forward = True

        # Update orientation based on the action
        if direction == 'R':
            current_orientation = (current_orientation + 1) % 4
        elif direction == 'L':
            current_orientation = (current_orientation - 1) % 4
        elif direction == 'B':
            current_orientation = (current_orientation + 2) % 4

        s1 = state_to_bucket(obv)
        s = s1
        reward += r1
        time += 1

    print(f"Simulation ended at time {time} with total reward = {reward}.")

train()
while True:
    d = input("Simulate? (y/n): ")
    if d.lower() == 'y':
        simulate()
    else:
        break
