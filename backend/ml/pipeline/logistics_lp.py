from ortools.linear_solver import pywraplp

BIG_M = 1e6     # penalty for unmet demand
PRIORITY = {"medicine": 1.0, "food": 0.7, "material": 0.3, "agri": 0.5}

def optimize_allocation(depots, villages, inventory, demand,
                        feasible, cost, commodities):
    """
    inventory : dict[(depot, commodity)] -> qty
    demand   : dict[(village, commodity)] -> qty
    feasible : dict[(depot, village)] -> bool
    cost     : dict[(depot, village)] -> float  (per-unit-km cost)
    """
    solver = pywraplp.Solver.CreateSolver("CBC")   # CBC handles MIP better than SCIP here

    x, unmet = {}, {}
    for d in depots:
        for v in villages:
            if not feasible.get((d, v), False):
                continue
            for c in commodities:
                x[d, v, c] = solver.NumVar(0, solver.infinity(), f"x_{d}_{v}_{c}")

    for v in villages:
        for c in commodities:
            unmet[v, c] = solver.NumVar(0, demand.get((v, c), 0), f"unmet_{v}_{c}")

    # Depot inventory per commodity
    for d in depots:
        for c in commodities:
            solver.Add(sum(x.get((d, v, c), 0) for v in villages)
                       <= inventory.get((d, c), 0))

    # Demand: served + unmet == demand  (equality forces LP to fill demand or pay penalty)
    for v in villages:
        for c in commodities:
            served = sum(x.get((d, v, c), 0) for d in depots)
            solver.Add(served + unmet[v, c] == demand.get((v, c), 0))

    # Objective: minimize routing cost + priority-weighted unmet penalty
    obj = solver.Objective()
    for (d, v, c), var in x.items():
        obj.SetCoefficient(var, cost[(d, v)])
    for (v, c), var in unmet.items():
        obj.SetCoefficient(var, BIG_M * PRIORITY.get(c, 0.5))
    obj.SetMinimization()

    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        return None

    allocations = {k: var.solution_value() for k, var in x.items()
                   if var.solution_value() > 1e-6}
    shortfall   = {k: var.solution_value() for k, var in unmet.items()
                   if var.solution_value() > 1e-6}
    return {"allocations": allocations, "shortfall": shortfall,
            "total_cost": solver.Objective().Value()}