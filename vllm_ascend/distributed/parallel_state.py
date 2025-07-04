from typing import Optional

import torch
from vllm.distributed.parallel_state import (GroupCoordinator, get_world_group,
                                             init_model_parallel_group)

# vllm-ascend will maintain its own EP GroupCoordinator and ETP GroupCoordinator for
# customize parallel solution
_EP: Optional[GroupCoordinator] = None
_ETP: Optional[GroupCoordinator] = None


def get_ep_group() -> GroupCoordinator:
    assert _EP is not None, ("expert model parallel group is not initialized")
    return _EP


def get_etp_group() -> GroupCoordinator:
    assert _ETP is not None, (
        "expert tensor parallel group is not initialized")
    return _ETP


def model_parallel_initialized():
    return (_ETP is not None and _EP is not None)


def init_ascend_model_parallel(
    expert_parallel_size: int = 1,
    expert_tensor_parallel_size: int = 1,
    world_size: Optional[int] = None,
    backend: Optional[str] = None,
):
    if model_parallel_initialized():
        return
    assert torch.distributed.is_initialized()
    world_size = torch.distributed.get_world_size()
    backend = backend or torch.distributed.get_backend(
        get_world_group().device_group)
    # num_expert_parallel_groups = expert_tensor_parallel_size
    # num_expert_tensor_parallel_groups = expert_parallel_size
    num_instance_count = world_size // expert_parallel_size // expert_tensor_parallel_size
    num_expert_parallel_groups_per_instance = expert_tensor_parallel_size
    num_expert_tensor_parallel_groups_per_instance = expert_parallel_size
    instance_size = expert_parallel_size * expert_tensor_parallel_size

    global _EP
    group_ranks = []
    # for i in range(num_expert_parallel_groups):
    #     ranks = list(range(i, world_size, num_expert_parallel_groups))
    #     group_ranks.append(ranks)
    for k in range(num_instance_count):
        instance_offset = k * instance_size
        for i in range(num_expert_parallel_groups_per_instance):
            ranks = list(range(i + instance_offset, i + instance_offset + instance_size, expert_tensor_parallel_size))
            group_ranks.append(ranks)

    _EP = init_model_parallel_group(group_ranks,
                                    get_world_group().local_rank,
                                    backend,
                                    group_name="ep")

    group_ranks = []
    global _ETP
    for k in range(num_instance_count):
        instance_offset = k * instance_size
        for i in range(num_expert_tensor_parallel_groups_per_instance):
            ranks = list(
                range(i * expert_tensor_parallel_size + instance_offset, (i + 1) * expert_tensor_parallel_size + instance_offset))
            group_ranks.append(ranks)

    _ETP = init_model_parallel_group(group_ranks,
                                     get_world_group().local_rank,
                                     backend,
                                     group_name="etp")


def destory_ascend_model_parallel():
    global _EP
    if _EP:
        _EP.destroy()
    _EP = None

    global _ETP
    if _ETP:
        _ETP.destroy()
    _ETP = None
