"""
What is free, what is taken, and what a step may be given.

The pool is what keeps the machine from being oversubscribed.  It hands out
reservations, and for an ordinary step the reservation is also the placement
its launch is given -- but the two are not the same idea, and the difference
matters where they diverge.  Memory is reserved and never placed, because no
launcher acts on it.  The pool's accounting has to cover everything a step
claims whether or not any of it reaches a launcher.

Three rules shape the packing and each of them is a constraint rather than a
total:

**A step that may not span nodes takes everything from one node.** An
allocation with cores free on several nodes and none of them holding enough
cannot start such a step, however much it shows free, and the pool says so
rather than deadlocking or overcommitting. Cores and GPUs come from the same
node: a step needing both must find both together.

**A step that may not span nodes takes them from the node the scheduler is
on.** Such a step does its work in its own process, and the only thing that
can confine that process is the executor, which can only reach the node it
is running on.  This caps Python concurrency at one node's worth of cores,
which is the ceiling Phase C exists to lift.

It is conservative for one case worth naming: an MPI step at width one may
not span by Polaris's default, and its launcher could perfectly well put it
on another node.  Two steps in Polaris are like that today.  The fix is for
such a step to declare ``may_span_nodes=True``, which is what the property
is for, rather than for the pool to guess from the shape of a step.

**A step's memory is charged in proportion to the cores it took on each
node.** A step that declares nothing is budgeted at its proportional share
of a node, so charging it proportionally means a run in which nothing
declares memory packs exactly as it would with no memory accounting at all.
Memory can then only ever remove a schedule that a measured declaration says
would not have fit.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from mache.parallel import ResourcePlacement

from polaris.run.allocation import NodeResources


@dataclass
class _Node:
    """What one node has left."""

    name: str
    free_cores: List[int]
    free_gpus: List[int]
    free_memory: Optional[int]
    memory: Optional[int]
    resident: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Reservation:
    """
    What a step was given, and what has to be handed back when it ends.

    Attributes
    ----------
    step_path : str
        The step this belongs to.

    placement : mache.parallel.ResourcePlacement
        Which nodes, cores and GPUs its launch is confined to.

    cores : dict
        The cores taken on each node, so that exactly those go back.

    gpus : dict
        The GPUs taken on each node.

    memory : dict
        The memory in MiB charged against each node.  Nothing acts on this
        but the pool: it is admission control and not a reservation the
        machine will honor.
    """

    step_path: str
    placement: ResourcePlacement
    cores: Dict[str, Tuple[int, ...]]
    gpus: Dict[str, Tuple[int, ...]]
    memory: Dict[str, int]


class ResourcePool:
    """
    The allocation's free resources, and what may be started against them.

    Attributes
    ----------
    local_node : str
        The node the scheduler itself is running on, which is the only one
        it can confine an unlaunched step to.
    """

    def __init__(
        self, nodes: List[NodeResources], local_node: Optional[str] = None
    ):
        """
        Parameters
        ----------
        nodes : list of polaris.run.allocation.NodeResources
            What the allocation holds, as its nodes reported it

        local_node : str, optional
            The node the scheduler is on.  Defaults to the first, which is
            where a batch script runs.
        """
        self._nodes = [
            _Node(
                name=node.name,
                free_cores=list(range(node.cores)),
                free_gpus=list(range(node.gpus)),
                free_memory=node.memory,
                memory=node.memory,
            )
            for node in nodes
        ]
        self._by_name = {node.name: node for node in self._nodes}
        self._held = list(nodes)
        if local_node is None:
            local_node = self._nodes[0].name if self._nodes else ''
        self.local_node = local_node

    def why_impossible(self, step) -> Optional[str]:
        """
        Say why a step could never run here, or ``None`` if it could.

        Asked once per step before anything starts, because a step that can
        never run should stop the run at second one rather than be
        discovered when its turn comes and never arrives.  It is asked
        against an empty copy of the allocation, so the answer is about the
        machine rather than about what happens to be running.

        Parameters
        ----------
        step : polaris.Step
            The step to ask about, with its resources already constrained
            against the whole allocation

        Returns
        -------
        reason : str or None
            What it needs that the allocation does not have
        """
        empty = ResourcePool(self._held, local_node=self.local_node)
        if empty.reserve(step) is not None:
            return None

        budget = step.memory_budget
        memory = 'no declared memory' if budget is None else f'{budget} MiB'
        if step.may_span_nodes:
            where = 'this allocation'
        else:
            where = (
                f'node {self.local_node}, which is the only one it may use '
                f'because it has not said its resources may span nodes'
            )
        return (
            f'Step {step.path} needs {step.cores} cores, {step.gpus or 0} '
            f'gpus and {memory}, which {where} cannot provide even with '
            f'nothing else running.'
        )

    def reserve(self, step) -> Optional[Reservation]:
        """
        Give a step what it needs, if what it needs is free right now.

        Parameters
        ----------
        step : polaris.Step
            The step to try to start, with its resources already
            constrained against the whole allocation

        Returns
        -------
        reservation : polaris.run.pool.Reservation or None
            What it was given, or ``None`` if it does not fit yet
        """
        if step.may_span_nodes:
            layout = self._fit_across_nodes(step)
        else:
            layout = self._fit_on_one_node(step)
        if layout is None:
            return None
        return self._take(step, layout)

    def release(self, reservation: Reservation) -> None:
        """
        Hand back everything a step was given.

        Parameters
        ----------
        reservation : polaris.run.pool.Reservation
            What the step held
        """
        for name, cores in reservation.cores.items():
            node = self._by_name[name]
            node.free_cores = sorted(node.free_cores + list(cores))
        for name, gpus in reservation.gpus.items():
            node = self._by_name[name]
            node.free_gpus = sorted(node.free_gpus + list(gpus))
        for name, memory in reservation.memory.items():
            node = self._by_name[name]
            if node.free_memory is not None:
                node.free_memory += memory
        for name in reservation.cores:
            resident = self._by_name[name].resident
            if reservation.step_path in resident:
                resident.remove(reservation.step_path)

    def resident(self, node_name: str) -> Tuple[str, ...]:
        """
        The steps on one node right now.

        This is what the report for a step killed by the node is built
        from: the victim is identifiable and the culprit is not, so naming
        the neighbors is the most that can honestly be said.

        Parameters
        ----------
        node_name : str
            The node to ask about

        Returns
        -------
        steps : tuple of str
            The paths of the steps resident on it
        """
        node = self._by_name.get(node_name)
        return () if node is None else tuple(node.resident)

    def _empty_view(self) -> List[_Node]:
        """The nodes as they would be with nothing running."""
        return [
            _Node(
                name=node.name,
                free_cores=list(range(len(node.free_cores))),
                free_gpus=list(range(len(node.free_gpus))),
                free_memory=node.memory,
                memory=node.memory,
            )
            for node in self._nodes
        ]

    def _fit_on_one_node(self, step):
        """Fit a step that has to take everything from the scheduler's node."""
        node = self._by_name.get(self.local_node)
        if node is None:
            return None
        cores = step.cores
        gpus = step.gpus or 0
        if len(node.free_cores) < cores or len(node.free_gpus) < gpus:
            return None
        charge = step.memory_budget
        if not _memory_fits(node, charge):
            return None
        return [
            (
                node,
                tuple(node.free_cores[:cores]),
                tuple(node.free_gpus[:gpus]),
                charge or 0,
            )
        ]

    def _fit_across_nodes(self, step):
        """
        Fit a step whose launcher spreads it over several nodes.

        The launchers distribute tasks evenly over the nodes they are given,
        so the nodes have to be able to serve that distribution rather than
        merely to add up: the cores a node provides are the cores of the
        tasks that land on it.  The fewest nodes that can do it is the
        answer, so that a step does not spread further than it must.
        """
        for count in range(1, len(self._nodes) + 1):
            layout = self._fit_on_n_nodes(step, count)
            if layout is not None:
                return layout
        return None

    def _fit_on_n_nodes(self, step, count):
        """Try to lay a step out over exactly ``count`` nodes."""
        total_cores = step.cores
        gpus = step.gpus or 0
        ntasks = max(step.ntasks or 1, 1)
        cpus_per_task = max(step.cpus_per_task or 1, 1)

        if ntasks > 1:
            # ranks fill each node in turn, and a node's cores are the cores
            # of the ranks that land on it
            tasks_per_node = -(-ntasks // count)
            wanted = [
                min(tasks_per_node, ntasks - index * tasks_per_node)
                * cpus_per_task
                for index in range(count)
            ]
            wanted = [cores for cores in wanted if cores > 0]
        else:
            # one process, so there are no ranks to spread; its cores are
            # divided as evenly as they go
            per_node = -(-total_cores // count)
            wanted = []
            left = total_cores
            for _ in range(count):
                take = min(per_node, left)
                if take > 0:
                    wanted.append(take)
                left -= take
        if sum(wanted) != total_cores:
            return None

        gpus_per_node = -(-gpus // len(wanted)) if wanted else 0
        chosen = self._choose_nodes(wanted, gpus_per_node)
        if chosen is None:
            return None

        gpu_ids = self._shared_gpu_ids(chosen, gpus_per_node)
        if gpu_ids is None:
            return None

        return self._charge_memory(step, chosen, wanted, gpu_ids, total_cores)

    def _choose_nodes(self, wanted, gpus_per_node):
        """Pick nodes that can serve each rank group, in pool order."""
        chosen: List[_Node] = []
        for node in self._nodes:
            if len(chosen) == len(wanted):
                break
            cores_here = wanted[len(chosen)]
            if len(node.free_cores) < cores_here:
                continue
            if len(node.free_gpus) < gpus_per_node:
                continue
            chosen.append(node)
        return chosen if len(chosen) == len(wanted) else None

    def _shared_gpu_ids(self, chosen, gpus_per_node):
        """
        The GPU indices to use, which are the same on every node.

        A placement carries one set of device indices for the whole launch,
        because that is what the machines which need them can express, and
        the indices are node-local.  So a launch spanning nodes has to use
        the same ones on each.
        """
        if gpus_per_node == 0:
            return ()
        shared = set(chosen[0].free_gpus)
        for node in chosen[1:]:
            shared &= set(node.free_gpus)
        if len(shared) < gpus_per_node:
            return None
        return tuple(sorted(shared)[:gpus_per_node])

    def _charge_memory(self, step, chosen, wanted, gpu_ids, total_cores):
        """
        Charge each node in proportion to the cores taken on it.

        Rounding goes to the last node so that the charges add up to the
        budget exactly rather than to a little less than it.

        A step on several nodes takes the *same* core numbers on each of
        them.  That is not tidiness, it is the only thing a launcher can
        express: Slurm's ``--cpu-bind=mask_cpu`` assigns masks by a task's
        index *on its own node* and reuses the list on every node, so the
        first node's masks are what every node applies.  Give two nodes
        different core sets and the second one silently runs on the first
        one's cores -- measured on Chrysalis, where three launches of
        omega_pr did exactly that and every one of them succeeded while the
        pool believed cores were free that were not.

        Taking a prefix of one shared ordering also serves the uneven case,
        where a node with fewer ranks needs fewer cores: its set is then the
        front of the same list, which is what the launcher would apply to it
        anyway.
        """
        budget = step.memory_budget or 0
        shared = _shared_cores(chosen) if len(chosen) > 1 else None
        layout = []
        charged = 0
        for index, node in enumerate(chosen):
            cores_here = wanted[index]
            available = node.free_cores if shared is None else shared
            if len(available) < cores_here:
                # the nodes are free enough separately but do not have these
                # cores free in common; another moment may do
                return None
            if index == len(chosen) - 1:
                charge = budget - charged
            else:
                charge = budget * cores_here // total_cores
            charged += charge
            if not _memory_fits(node, charge if step.memory_budget else None):
                return None
            layout.append(
                (
                    node,
                    tuple(available[:cores_here]),
                    gpu_ids,
                    charge,
                )
            )
        return layout

    def _take(self, step, layout) -> Reservation:
        """Remove what a layout uses from the pool and describe it."""
        cores: Dict[str, Tuple[int, ...]] = {}
        gpus: Dict[str, Tuple[int, ...]] = {}
        memory: Dict[str, int] = {}
        for node, node_cores, node_gpus, charge in layout:
            node.free_cores = [
                core for core in node.free_cores if core not in node_cores
            ]
            node.free_gpus = [
                gpu for gpu in node.free_gpus if gpu not in node_gpus
            ]
            if node.free_memory is not None:
                node.free_memory -= charge
            node.resident.append(step.path)
            cores[node.name] = node_cores
            gpus[node.name] = node_gpus
            memory[node.name] = charge

        names = tuple(node.name for node, _, _, _ in layout)
        # A placement's device indices are node-local and its GPU count is a
        # total, so the two can only agree for a launch on one node: two
        # nodes using devices 0-3 each is four indices against a total of
        # eight.  So the indices are named only for a single-node launch,
        # and a launch spanning nodes leaves them to the scheduler.
        #
        # That costs nothing where the batch system assigns GPUs, which is
        # every Slurm machine.  On PALS nothing reserves a GPU in the first
        # place, so a spanning launch there sees every device on its nodes.
        # Worth knowing before a GPU step is ever run wider than a node on
        # Aurora; nothing does today.
        gpu_ids = layout[0][2] if len(layout) == 1 else None
        placement = ResourcePlacement(
            nodes=tuple(name for name in names if name != ''),
            cores=tuple(node_cores for _, node_cores, _, _ in layout),
            gpus=step.gpus or 0,
            gpu_ids=gpu_ids or None,
        )
        return Reservation(
            step_path=step.path,
            placement=placement,
            cores=cores,
            gpus=gpus,
            memory=memory,
        )


def _shared_cores(chosen: List[_Node]) -> List[int]:
    """The cores free on every one of these nodes, in a stable order."""
    common = set(chosen[0].free_cores)
    for node in chosen[1:]:
        common &= set(node.free_cores)
    return sorted(common)


def _memory_fits(node: _Node, charge: Optional[int]) -> bool:
    """Whether a node can carry this much more memory."""
    if charge is None or node.free_memory is None:
        # a machine that has not said how much memory a node holds cannot
        # have memory accounted for, and packs on cores as it always did
        return True
    return charge <= node.free_memory
