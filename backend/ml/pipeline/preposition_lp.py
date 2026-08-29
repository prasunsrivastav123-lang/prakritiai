from ortools.linear_solver import pywraplp
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def optimize_prepositioning(depots, villages, current_inventory, future_demand, transport_cost):
    """
    Moves supplies BEFORE the disaster hits.
    transport_cost: dict[(depot, village)] -> cost per unit
    """
    solver = pywraplp.Solver.CreateSolver("CBC")
    x = {}
    
    for d in depots:
        for v in villages:
            x[d, v] = solver.NumVar(0, solver.infinity(), f"preposition_{d}_{v}")
            
    # Constraint 1: Cannot move more than what the depot currently holds
    for d in depots:
        solver.Add(sum(x[d, v] for v in villages) <= current_inventory.get(d, 0))
        
    # Constraint 2: Try to meet future demand at the village
    for v in villages:
        solver.Add(sum(x[d, v] for d in depots) <= future_demand.get(v, 0))
        
    # Objective: Minimize cost of moving supplies early
    obj = solver.Objective()
    for (d, v), var in x.items():
        obj.SetCoefficient(var, transport_cost.get((d, v), 999))
    obj.SetMinimization()
    
    if solver.Solve() == pywraplp.Solver.OPTIMAL:
        logging.info("Prepositioning LP solved successfully.")
        return {k: var.solution_value() for k, var in x.items() if var.solution_value() > 0}
    return {}