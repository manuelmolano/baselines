"""
Helpers for scripts like run_atari.py.
"""

import os
try:
    from mpi4py import MPI
except ImportError:
    MPI = None

import gym
from gym.wrappers import FlattenDictWrapper
from baselines import logger
from baselines.bench import Monitor
from baselines.common import set_global_seeds
from baselines.common.atari_wrappers import make_atari, wrap_deepmind
from baselines.common.vec_env.subproc_vec_env import SubprocVecEnv
from baselines.common.vec_env.dummy_vec_env import DummyVecEnv
from baselines.common import retro_wrappers


def make_vec_env(env_id, env_type, num_env, seed,
                 wrapper_kwargs=None,
                 start_index=0,
                 reward_scale=1.0,
                 flatten_dict_observations=True,
                 gamestate=None):
    """
    Create a wrapped, monitored SubprocVecEnv for Atari and MuJoCo.
    """
    wrapper_kwargs = wrapper_kwargs or {}
    mpi_rank = MPI.COMM_WORLD.Get_rank() if MPI else 0
    seed = seed + 10000 * mpi_rank if seed is not None else None
    fdo = flatten_dict_observations

    def make_thunk(rank):
        return lambda: make_env(env_id=env_id,
                                env_type=env_type,
                                subrank=rank,
                                seed=seed,
                                reward_scale=reward_scale,
                                gamestate=gamestate,
                                flatten_dict_observations=fdo,
                                wrapper_kwargs=wrapper_kwargs)

    set_global_seeds(seed)
    if num_env > 1:
        return SubprocVecEnv([make_thunk(i + start_index)
                              for i in range(num_env)])
    else:
        return DummyVecEnv([make_thunk(start_index)])


def make_env(env_id, env_type, subrank=0, seed=None, reward_scale=1.0,
             gamestate=None, flatten_dict_observations=True,
             wrapper_kwargs=None):
    mpi_rank = MPI.COMM_WORLD.Get_rank() if MPI else 0
    wrapper_kwargs = wrapper_kwargs or {}
    if env_type == 'atari':
        env = make_atari(env_id)
    elif env_type == 'retro':
        import retro
        gamestate = gamestate or retro.State.DEFAULT
        rad = retro.Actions.DISCRETE
        env = retro_wrappers.make_retro(game=env_id, max_episode_steps=10000,
                                        use_restricted_actions=rad,
                                        state=gamestate)
    else:
        env = gym.make(env_id)

    if flatten_dict_observations and\
       isinstance(env.observation_space, gym.spaces.Dict):
        keys = env.observation_space.spaces.keys()
        env = gym.wrappers.FlattenDictWrapper(env, dict_keys=list(keys))

    env.seed(seed + subrank if seed is not None else None)

    # priors task parameters
    if env_id == 'priors-v0':
        env.update_params(wrapper_kwargs)

    env = Monitor(env, logger.get_dir() and os.path.join(logger.get_dir(),
                  str(mpi_rank) + '.' + str(subrank)),
                  allow_early_resets=True)

    if env_type == 'atari':
        env = wrap_deepmind(env, **wrapper_kwargs)
    elif env_type == 'retro':
        env = retro_wrappers.wrap_deepmind_retro(env, **wrapper_kwargs)

    if reward_scale != 1:
        env = retro_wrappers.RewardScaler(env, reward_scale)

    return env


def make_mujoco_env(env_id, seed, reward_scale=1.0):
    """
    Create a wrapped, monitored gym.Env for MuJoCo.
    """
    rank = MPI.COMM_WORLD.Get_rank()
    myseed = seed + 1000 * rank if seed is not None else None
    set_global_seeds(myseed)
    env = gym.make(env_id)
    lgd = logger.get_dir()
    logger_path = None if lgd is None else os.path.join(lgd, str(rank))
    env = Monitor(env, logger_path, allow_early_resets=True)
    env.seed(seed)
    if reward_scale != 1.0:
        from baselines.common.retro_wrappers import RewardScaler
        env = RewardScaler(env, reward_scale)
    return env


def make_robotics_env(env_id, seed, rank=0):
    """
    Create a wrapped, monitored gym.Env for MuJoCo.
    """
    set_global_seeds(seed)
    env = gym.make(env_id)
    env = FlattenDictWrapper(env, ['observation', 'desired_goal'])
    env = Monitor(
        env, logger.get_dir() and os.path.join(logger.get_dir(), str(rank)),
        info_keywords=('is_success',))
    env.seed(seed)
    return env


def arg_parser():
    """
    Create an empty argparse.ArgumentParser.
    """
    import argparse
    adhf = argparse.ArgumentDefaultsHelpFormatter
    return argparse.ArgumentParser(formatter_class=adhf)


def atari_arg_parser():
    """
    Create an argparse.ArgumentParser for run_atari.py.
    """
    print('Obsolete - use common_arg_parser instead')
    return common_arg_parser()


def mujoco_arg_parser():
    print('Obsolete - use common_arg_parser instead')
    return common_arg_parser()


def common_arg_parser():
    """
    Create an argparse.ArgumentParser for run_mujoco.py.
    """
    parser = arg_parser()
    parser.add_argument('--env', help='environment ID', type=str,
                        default='Reacher-v2')
    parser.add_argument('--seed', help='RNG seed', type=int, default=None)
    parser.add_argument('--alg', help='Algorithm', type=str, default='ppo2')
    parser.add_argument('--num_timesteps', type=float, default=1e6),
    parser.add_argument('--network', help='network type (mlp, cnn, lstm,' +
                        ' cnn_lstm, conv_only)', default=None)
    parser.add_argument('--gamestate', help='game state to load' +
                        ' (so far only used in retro games)', default=None)
    parser.add_argument('--num_env', help='Number of environment copies' +
                        ' being run in parallel. When not specified, set' +
                        ' to number of cpus for Atari, and to 1 for Mujoco',
                        default=None, type=int)
    parser.add_argument('--reward_scale', help='Reward scale factor.' +
                        ' Default: 1.0', default=1.0, type=float)
    parser.add_argument('--save_path', help='Path to save trained model to',
                        default=None, type=str)
    parser.add_argument('--save_video_interval', help='Save video' +
                        ' every x steps (0 = disabled)', default=0, type=int)
    parser.add_argument('--save_video_length', help='Length of recorded' +
                        ' video. Default: 200', default=200, type=int)
    parser.add_argument('--play', default=False, action='store_true')
    parser.add_argument('--extra_import', help='Extra module to import to' +
                        ' access external environments', type=str,
                        default=None)
    # priors task parameters
    parser.add_argument('--exp_dur', help='exp. duration in num. of trials',
                        type=int, default=100)
    parser.add_argument('--trial_dur', help='num. of steps in each trial',
                        type=int, default=10)
    parser.add_argument('-r', '--reward',
                        help='rewards for: stop fix, fix, hit, fail',
                        type=float, nargs='+', default=(-0.1, 0.0, 1.0, -1.0))
    parser.add_argument('--block_dur', help='num. of trials x block', type=int,
                        default=200)
    parser.add_argument('--stim_ev', help='level of difficulty of the exp.',
                        type=float, default=0.5)
    parser.add_argument('-rp', '--rep_prob', help='rep. prob. for each block',
                        type=float, nargs='+', default=(.2, .8))
    parser.add_argument('--folder', help='where to save the data',
                        type=str, default='')
    return parser


def robotics_arg_parser():
    """
    Create an argparse.ArgumentParser for run_mujoco.py.
    """
    parser = arg_parser()
    parser.add_argument('--env', help='environment ID', type=str,
                        default='FetchReach-v0')
    parser.add_argument('--seed', help='RNG seed', type=int, default=None)
    parser.add_argument('--num-timesteps', type=int, default=int(1e6))
    return parser


def parse_unknown_args(args):
    """
    Parse arguments not consumed by arg parser into a dicitonary
    """
    retval = {}
    preceded_by_key = False
    for arg in args:
        if arg.startswith('--'):
            if '=' in arg:
                key = arg.split('=')[0][2:]
                value = arg.split('=')[1]
                retval[key] = value
            else:
                key = arg[2:]
                preceded_by_key = True
        elif preceded_by_key:
            retval[key] = arg
            preceded_by_key = False

    return retval
