"""Low-cost PyBullet 3D arm twin driven by debounced gesture commands.

Install the dependency with:
    uv pip install pybullet

Typical integration with the existing OpenCV loop:

    import pybullet as p
    from arm_pybullet import PyBulletArm

    arm = PyBulletArm()
    try:
        while True:
            # ... read camera, run MediaPipe, debounce ...
            command = debounced.active_command
            arm.update(command)
            p.stepSimulation(physicsClientId=arm.client_id)
    finally:
        arm.close()
"""

from __future__ import annotations

from dataclasses import dataclass
import time

import pybullet as p
import pybullet_data


@dataclass(frozen=True)
class Bounds3D:
    x: tuple[float, float]
    y: tuple[float, float]
    z: tuple[float, float]


class PyBulletArm:
    """Small GUI-mode PyBullet twin using the bundled Franka Panda model."""

    def __init__(self, gui: bool = True, time_step: float = 1.0 / 60.0) -> None:
        mode = p.GUI if gui else p.DIRECT
        self.client_id = p.connect(mode, options="--width=640 --height=480")
        if self.client_id < 0:
            raise RuntimeError("Could not connect to PyBullet")

        self.robot_id: int | None = None
        self.control_joints: list[int] = []
        self.lower_limits: list[float] = []
        self.upper_limits: list[float] = []
        self.joint_ranges: list[float] = []
        self.end_effector_index = 11
        self.time_step = time_step
        self.mode = "CARTESIAN"
        self._toggle_latched = False
        self._held_joint_targets: list[float] | None = None

        self.home_joints = [0.0, -0.55, 0.0, -2.25, 0.0, 1.75, 0.75]
        self.target_pos = [0.45, 0.0, 0.45]
        self.target_orn = p.getQuaternionFromEuler((0.0, 1.57, 0.0))
        self.bounds = Bounds3D(x=(0.25, 0.70), y=(-0.30, 0.30), z=(0.15, 0.75))

        self._setup_world()

    def update(self, command: str | None) -> None:
        """Apply one bounded command step and send joint targets to PyBullet."""
        if command is None or command == "STOP":
            self._toggle_latched = False
            self._hold_position()
            return

        self._held_joint_targets = None

        if command in {"TOGGLE", "TOGGLE_MODE"} and not self._toggle_latched:
            self.mode = "JOINT" if self.mode == "CARTESIAN" else "CARTESIAN"
            self._toggle_latched = True
        elif command not in {"TOGGLE", "TOGGLE_MODE"}:
            self._toggle_latched = False

        if command == "HOME":
            self.reset_home()
            return

        if self.mode == "JOINT":
            self._update_joint_mode(command)
        else:
            self._update_cartesian_mode(command)

    def reset_home(self) -> None:
        """Return the simulated arm and IK target to a known reachable pose."""
        if self.robot_id is None:
            return

        for joint_index, angle in zip(self.control_joints, self.home_joints):
            p.resetJointState(
                self.robot_id,
                joint_index,
                angle,
                physicsClientId=self.client_id,
            )

        self.target_pos = [0.45, 0.0, 0.45]
        self.mode = "CARTESIAN"
        self._toggle_latched = False
        self._held_joint_targets = None
        self._apply_ik_target()

    def close(self) -> None:
        if p.isConnected(self.client_id):
            p.disconnect(self.client_id)

    def _setup_world(self) -> None:
        p.configureDebugVisualizer(
            p.COV_ENABLE_RENDERING,
            0,
            physicsClientId=self.client_id,
        )
        p.configureDebugVisualizer(
            p.COV_ENABLE_GUI,
            0,
            physicsClientId=self.client_id,
        )
        p.configureDebugVisualizer(
            p.COV_ENABLE_SHADOWS,
            0,
            physicsClientId=self.client_id,
        )
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=self.client_id)
        p.setGravity(0.0, 0.0, -9.81, physicsClientId=self.client_id)
        p.setTimeStep(self.time_step, physicsClientId=self.client_id)
        p.setRealTimeSimulation(0, physicsClientId=self.client_id)

        p.loadURDF("plane.urdf", physicsClientId=self.client_id)
        self.robot_id = p.loadURDF(
            "franka_panda/panda.urdf",
            basePosition=(0.0, 0.0, 0.0),
            useFixedBase=True,
            physicsClientId=self.client_id,
        )
        self.control_joints = self._movable_joint_indices()
        self.lower_limits, self.upper_limits = self._joint_limits()
        self.joint_ranges = [
            upper - lower for lower, upper in zip(self.lower_limits, self.upper_limits)
        ]
        self.reset_home()

        p.resetDebugVisualizerCamera(
            cameraDistance=1.45,
            cameraYaw=45.0,
            cameraPitch=-32.0,
            cameraTargetPosition=(0.35, 0.0, 0.40),
            physicsClientId=self.client_id,
        )
        p.configureDebugVisualizer(
            p.COV_ENABLE_RENDERING,
            1,
            physicsClientId=self.client_id,
        )

    def _movable_joint_indices(self) -> list[int]:
        if self.robot_id is None:
            return []

        joints: list[int] = []
        for joint_index in range(p.getNumJoints(self.robot_id, physicsClientId=self.client_id)):
            joint_info = p.getJointInfo(
                self.robot_id,
                joint_index,
                physicsClientId=self.client_id,
            )
            if joint_info[2] in (p.JOINT_REVOLUTE, p.JOINT_PRISMATIC):
                joints.append(joint_index)
        return joints[:7]

    def _update_cartesian_mode(self, command: str) -> None:
        step = 0.025
        if command in {"STEP_X_POS", "STEP_X"}:
            self.target_pos[0] += step
        elif command == "STEP_X_NEG":
            self.target_pos[0] -= step
        elif command in {"STEP_Y_POS"}:
            self.target_pos[1] += step
        elif command in {"STEP_Y_NEG"}:
            self.target_pos[1] -= step
        elif command == "STEP_YAW_POS":
            self._step_wrist_yaw(step)
            return
        elif command == "STEP_YAW_NEG":
            self._step_wrist_yaw(-step)
            return
        elif command in {"STEP_Z_POS", "STEP_Z_PLUS"}:
            self.target_pos[2] += step
        elif command in {"STEP_Z_NEG", "STEP_Z_MINUS"}:
            self.target_pos[2] -= step

        self.target_pos = [
            self._clip(self.target_pos[0], self.bounds.x),
            self._clip(self.target_pos[1], self.bounds.y),
            self._clip(self.target_pos[2], self.bounds.z),
        ]
        self._apply_ik_target()

    def _update_joint_mode(self, command: str) -> None:
        if self.robot_id is None:
            return

        joint_states = p.getJointStates(
            self.robot_id,
            self.control_joints,
            physicsClientId=self.client_id,
        )
        targets = [state[0] for state in joint_states]
        step = 0.045

        if command in {"STEP_X_POS", "STEP_X"}:
            targets[0] += step
        elif command == "STEP_X_NEG":
            targets[0] -= step
        elif command in {"STEP_Z_POS", "STEP_Z_PLUS"}:
            targets[1] += step
            targets[3] -= step
        elif command in {"STEP_Z_NEG", "STEP_Z_MINUS"}:
            targets[1] -= step
            targets[3] += step
        elif command == "STEP_YAW_POS":
            targets[6] += step
        elif command == "STEP_YAW_NEG":
            targets[6] -= step

        targets = [
            self._clip(target, (lower, upper))
            for target, lower, upper in zip(
                targets,
                self.lower_limits,
                self.upper_limits,
            )
        ]
        self._send_joint_targets(targets, force=90.0)
        self._sync_target_to_end_effector()

    def _step_wrist_yaw(self, delta: float) -> None:
        if self.robot_id is None or len(self.control_joints) < 7:
            return

        joint_states = p.getJointStates(
            self.robot_id,
            self.control_joints,
            physicsClientId=self.client_id,
        )
        targets = [state[0] for state in joint_states]
        targets[6] = self._clip(
            targets[6] + delta,
            (self.lower_limits[6], self.upper_limits[6]),
        )
        self._send_joint_targets(targets, force=70.0)

    def _apply_ik_target(self) -> None:
        if self.robot_id is None:
            return

        rest_poses = self.home_joints[: len(self.control_joints)]
        joint_targets = p.calculateInverseKinematics(
            self.robot_id,
            self.end_effector_index,
            self.target_pos,
            self.target_orn,
            lowerLimits=self.lower_limits,
            upperLimits=self.upper_limits,
            jointRanges=self.joint_ranges,
            restPoses=rest_poses,
            maxNumIterations=35,
            residualThreshold=0.004,
            physicsClientId=self.client_id,
        )
        self._send_joint_targets(joint_targets[: len(self.control_joints)], force=80.0)

    def _hold_position(self) -> None:
        if self.robot_id is None:
            return
        if self._held_joint_targets is None:
            joint_states = p.getJointStates(
                self.robot_id,
                self.control_joints,
                physicsClientId=self.client_id,
            )
            self._held_joint_targets = [state[0] for state in joint_states]
            for joint_index, target in zip(self.control_joints, self._held_joint_targets):
                p.resetJointState(
                    self.robot_id,
                    joint_index,
                    target,
                    targetVelocity=0.0,
                    physicsClientId=self.client_id,
                )
            self._sync_target_to_end_effector()

        self._send_joint_targets(
            self._held_joint_targets,
            force=500.0,
            position_gain=0.6,
            velocity_gain=1.0,
        )

    def _send_joint_targets(
        self,
        targets: list[float] | tuple[float, ...],
        force: float,
        position_gain: float = 0.06,
        velocity_gain: float = 0.8,
    ) -> None:
        if self.robot_id is None:
            return

        p.setJointMotorControlArray(
            self.robot_id,
            self.control_joints,
            p.POSITION_CONTROL,
            targetPositions=list(targets),
            targetVelocities=[0.0] * len(self.control_joints),
            forces=[force] * len(self.control_joints),
            positionGains=[position_gain] * len(self.control_joints),
            velocityGains=[velocity_gain] * len(self.control_joints),
            physicsClientId=self.client_id,
        )

    def _joint_limits(self) -> tuple[list[float], list[float]]:
        if self.robot_id is None:
            return [], []

        lower_limits: list[float] = []
        upper_limits: list[float] = []
        for joint_index in self.control_joints:
            joint_info = p.getJointInfo(
                self.robot_id,
                joint_index,
                physicsClientId=self.client_id,
            )
            lower = float(joint_info[8])
            upper = float(joint_info[9])
            if lower >= upper:
                lower, upper = -3.14, 3.14
            lower_limits.append(lower)
            upper_limits.append(upper)
        return lower_limits, upper_limits

    def _sync_target_to_end_effector(self) -> None:
        if self.robot_id is None:
            return
        link_state = p.getLinkState(
            self.robot_id,
            self.end_effector_index,
            physicsClientId=self.client_id,
        )
        pos = link_state[0]
        self.target_pos = [
            self._clip(pos[0], self.bounds.x),
            self._clip(pos[1], self.bounds.y),
            self._clip(pos[2], self.bounds.z),
        ]

    @staticmethod
    def _clip(value: float, bounds: tuple[float, float]) -> float:
        return max(bounds[0], min(bounds[1], value))


if __name__ == "__main__":
    arm = PyBulletArm()
    commands = ["HOME", "STEP_Z_POS", "STEP_X_POS", "STEP_Z_NEG", "TOGGLE_MODE"]
    index = 0
    try:
        while p.isConnected(arm.client_id):
            arm.update(commands[index // 90 % len(commands)])
            p.stepSimulation(physicsClientId=arm.client_id)
            index += 1
            time.sleep(arm.time_step)
    finally:
        arm.close()
