"""待机小动作：伸懒腰 / 挠痒 / 打哈欠，全员通用，BehaviorFSM 构造时无条件挂载。

三个态都从 IdleStand 经心情仲裁抽中进入，自行走完包络再交回 IdleStand，
不移动坐标、不耗体力，只改姿态（gfx.idle_act）与单手 IK（gfx.hand_aim）。
姿态形变本身在 rendering/graphics._apply_idle_act_pose，这里只管时序与选择。
"""
from __future__ import annotations
import math

from . import tuning
from .desire import Candidate, play_mult

# 三态名，供 fsm 能量表与清理判据引用
ACTS = ("IdleStretch", "IdleScratch", "IdleYawn")


def _lerp(x, lo, hi, flo, fhi):
    if hi == lo:
        return flo
    t = max(0.0, min(1.0, (x - lo) / (hi - lo)))
    return flo + (fhi - flo) * t


def _envelope(timer, dur, rise, fall) -> float:
    """0→1→0 强度包络：rise 起势、中段保持、fall 收势，smoothstep 平滑。"""
    if timer <= 0:
        return 0.0
    if timer < rise:
        t = timer / rise
    elif timer > dur - fall:
        t = max(0.0, (dur - timer) / fall)
    else:
        t = 1.0
    return t * t * (3.0 - 2.0 * t)


def _clear(fsm):
    """复位姿态与本模块占用的那只手，别的系统的 hand_aim 不碰。"""
    fsm.gfx.idle_act = None
    side = getattr(fsm, "_idleact_hand", None)
    if side is not None:
        fsm.gfx.hand_aim[side] = None
        fsm._idleact_hand = None


def _enter_common(fsm):
    fsm.body.set_posture(True)
    fsm.body.stop_walk()
    # 小动作之间直接转态时不走 brk，这里补一次放手，免得上一式的手一直钉着
    side = getattr(fsm, "_idleact_hand", None)
    if side is not None:
        fsm.gfx.hand_aim[side] = None
        fsm._idleact_hand = None


def _interrupted(fsm) -> bool:
    """被抓走或脚下踏空：复位并交还对应态。游泳/零重力由 update() 前置强转接管。"""
    if fsm.grab.active:
        _clear(fsm)
        fsm._transition("Dragged")
        return True
    if not fsm.body.on_floor():
        _clear(fsm)
        fsm._transition("Airborne")
        return True
    return False


def _mount_stretch(fsm):
    """伸懒腰 IdleStretch：拱背前伸，头自己抬着不追视。"""

    def enter():
        _enter_common(fsm)
        fsm.gfx.idle_act = ("stretch", 0.0, 0.0)

    def tick(cursor, disturbed):
        if _interrupted(fsm):
            return
        a = _envelope(fsm.timer, tuning.STRETCH_TICKS,
                      tuning.STRETCH_RISE, tuning.STRETCH_FALL)
        fsm.gfx.idle_act = ("stretch", a, 0.0)
        fsm.gfx.look_at = None
        if fsm.timer >= tuning.STRETCH_TICKS:
            brk()
            fsm._transition("IdleStand")

    def brk():
        _clear(fsm)

    fsm.register_state("IdleStretch", enter=enter, tick=tick, brk=brk, kill_break=brk,
                       mood="idle_stretch")
    fsm.mood.add(Candidate(
        "idle_stretch", base=tuning.STRETCH_BASE * play_mult(fsm.pers, "idle_stretch"),
        start=tuning.STRETCH_START, quit=0.0,
        decay=tuning.STRETCH_DECAY, recover=tuning.STRETCH_RECOVER,
        gate=lambda ctx: not ctx.submerged and ctx.energy >= tuning.IDLEACT_ENERGY_GATE,
        energy_factor=lambda e: _lerp(e, 0.0, 1.0,
                                      tuning.STRETCH_SF_TIRED, tuning.STRETCH_SF_FRESH),
        temper_factor=lambda t: 1.0,
        one_shot=True, init=tuning.STRETCH_INIT))


def _mount_scratch(fsm):
    """挠痒 IdleScratch：近侧手够到头顶侧方，按正弦抖。"""

    def enter():
        _enter_common(fsm)
        fsm.gfx.idle_act = ("scratch", 0.0, 0.0)

    def tick(cursor, disturbed):
        if _interrupted(fsm):
            return
        a = _envelope(fsm.timer, tuning.SCRATCH_TICKS,
                      tuning.SCRATCH_RISE, tuning.SCRATCH_FALL)
        phase = fsm.timer / tuning.SCRATCH_PERIOD
        fsm.gfx.idle_act = ("scratch", a, phase)
        g = fsm.gfx
        flip = fsm.body.facing
        side = "r" if flip > 0 else "l"
        if a > 0.05:
            # 换边时先把上一只手放回，免得两手同时被钉住
            prev = getattr(fsm, "_idleact_hand", None)
            if prev is not None and prev != side:
                g.hand_aim[prev] = None
            jig = math.sin(phase * 2.0 * math.pi)
            g.hand_aim[side] = (
                g.head.x + flip * (tuning.SCRATCH_REACH_X + tuning.SCRATCH_JIG_X * jig) * a,
                g.head.y + (tuning.SCRATCH_REACH_Y + tuning.SCRATCH_JIG_Y * jig) * a)
            fsm._idleact_hand = side
        if fsm.timer >= tuning.SCRATCH_TICKS:
            brk()
            fsm._transition("IdleStand")

    def brk():
        _clear(fsm)

    fsm.register_state("IdleScratch", enter=enter, tick=tick, brk=brk, kill_break=brk,
                       mood="idle_scratch")
    fsm.mood.add(Candidate(
        "idle_scratch", base=tuning.SCRATCH_BASE * play_mult(fsm.pers, "idle_scratch"),
        start=tuning.SCRATCH_START, quit=0.0,
        decay=tuning.SCRATCH_DECAY, recover=tuning.SCRATCH_RECOVER,
        gate=lambda ctx: not ctx.submerged and ctx.energy >= tuning.IDLEACT_ENERGY_GATE,
        energy_factor=lambda e: 1.0,
        temper_factor=lambda t: _lerp(t, -1.0, 1.0,
                                      tuning.SCRATCH_TF_GRUMPY, tuning.SCRATCH_TF_FOND),
        one_shot=True, init=tuning.SCRATCH_INIT))


def _mount_yawn(fsm):
    """打哈欠 IdleYawn：后仰抬头，包络过线眯眼。"""

    def enter():
        _enter_common(fsm)
        fsm.gfx.idle_act = ("yawn", 0.0, 0.0)

    def tick(cursor, disturbed):
        if _interrupted(fsm):
            return
        a = _envelope(fsm.timer, tuning.YAWN_TICKS, tuning.YAWN_RISE, tuning.YAWN_FALL)
        fsm.gfx.idle_act = ("yawn", a, 0.0)
        if a >= tuning.YAWN_EYES_SHUT:
            fsm.gfx.blink = max(fsm.gfx.blink, 2)   # 每 tick 顶住，盖过 _update_blink 自减
        if fsm.timer >= tuning.YAWN_TICKS:
            brk()
            fsm._transition("IdleStand")

    def brk():
        _clear(fsm)

    fsm.register_state("IdleYawn", enter=enter, tick=tick, brk=brk, kill_break=brk,
                       mood="idle_yawn")
    fsm.mood.add(Candidate(
        "idle_yawn", base=tuning.YAWN_BASE,
        start=tuning.YAWN_START, quit=0.0,
        decay=tuning.YAWN_DECAY, recover=tuning.YAWN_RECOVER,
        # 频率由 decay/recover 定，权重只在同场竞争时起作用——
        # 所以「越困越常打哈欠」得靠闸门：精神头足时根本不进候选池
        gate=lambda ctx: not ctx.submerged and ctx.energy <= tuning.YAWN_ENERGY_MAX,
        energy_factor=lambda e: _lerp(e, 0.0, 1.0,
                                      tuning.YAWN_SF_TIRED, tuning.YAWN_SF_FRESH),
        temper_factor=lambda t: 1.0,
        one_shot=True, init=tuning.YAWN_INIT))


def _tick_cleanup(fsm):
    """兜底复位：update() 里有几处（如被抓）不走 brk 直接转态，姿态得有人收。"""
    if fsm.gfx.idle_act is not None and fsm.state not in ACTS:
        _clear(fsm)


def mount(fsm):
    """BehaviorFSM 构造时调用，先于 CatDef.fsm_mount。"""
    fsm._idleact_hand = None       # 本模块占用中的那只手，None=没占
    _mount_stretch(fsm)
    _mount_scratch(fsm)
    _mount_yawn(fsm)
    fsm.register_ticker(lambda: _tick_cleanup(fsm))
