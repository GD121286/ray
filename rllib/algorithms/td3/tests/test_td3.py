import numpy as np
import unittest

import ray
import ray.rllib.algorithms.td3 as td3
from ray.rllib.utils.framework import try_import_tf
from ray.rllib.utils.test_utils import (
    check,
    check_compute_single_action,
    check_train_results,
    framework_iterator,
)

tf1, tf, tfv = try_import_tf()


class TestTD3(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ray.init()

    @classmethod
    def tearDownClass(cls) -> None:
        ray.shutdown()

    def test_td3_compilation(self):
        """Test whether TD3 can be built with both frameworks."""
        config = td3.TD3Config()

        # Test against all frameworks.
        for _ in framework_iterator(config, with_eager_tracing=True):
            trainer = config.build(env="Pendulum-v1")
            num_iterations = 1
            for i in range(num_iterations):
                results = trainer.train()
                check_train_results(results)
                print(results)
            check_compute_single_action(trainer)
            trainer.stop()

    def test_td3_exploration_and_with_random_prerun(self):
        """Tests TD3's Exploration (w/ random actions for n timesteps)."""
        config = td3.TD3Config().environment(env="Pendulum-v1")
        no_random_init = config.exploration_config.copy()
        random_init = {
            # Act randomly at beginning ...
            "random_timesteps": 30,
            # Then act very closely to deterministic actions thereafter.
            "stddev": 0.001,
            "initial_scale": 0.001,
            "final_scale": 0.001,
        }
        obs = np.array([0.0, 0.1, -0.1])

        # Test against all frameworks.
        for _ in framework_iterator(config, with_eager_tracing=True):
            config.exploration(exploration_config=no_random_init)
            # Default GaussianNoise setup.
            trainer = config.build()
            # Setting explore=False should always return the same action.
            a_ = trainer.compute_single_action(obs, explore=False)
            check(trainer.get_policy().global_timestep, 1)
            for i in range(50):
                a = trainer.compute_single_action(obs, explore=False)
                check(trainer.get_policy().global_timestep, i + 2)
                check(a, a_)
            # explore=None (default: explore) should return different actions.
            actions = []
            for i in range(50):
                actions.append(trainer.compute_single_action(obs))
                check(trainer.get_policy().global_timestep, i + 52)
            check(np.std(actions), 0.0, false=True)
            trainer.stop()

            # Check randomness at beginning.
            config.exploration(exploration_config=random_init)
            trainer = config.build()
            # ts=0 (get a deterministic action as per explore=False).
            deterministic_action = trainer.compute_single_action(obs, explore=False)
            check(trainer.get_policy().global_timestep, 1)
            # ts=1-29 (in random window).
            random_a = []
            for i in range(1, 30):
                random_a.append(trainer.compute_single_action(obs, explore=True))
                check(trainer.get_policy().global_timestep, i + 1)
                check(random_a[-1], deterministic_action, false=True)
            self.assertTrue(np.std(random_a) > 0.3)

            # ts > 30 (a=deterministic_action + scale * N[0,1])
            for i in range(50):
                a = trainer.compute_single_action(obs, explore=True)
                check(trainer.get_policy().global_timestep, i + 31)
                check(a, deterministic_action, rtol=0.1)

            # ts >> 30 (BUT: explore=False -> expect deterministic action).
            for i in range(50):
                a = trainer.compute_single_action(obs, explore=False)
                check(trainer.get_policy().global_timestep, i + 81)
                check(a, deterministic_action)
            trainer.stop()


if __name__ == "__main__":
    import pytest
    import sys

    sys.exit(pytest.main(["-v", __file__]))
