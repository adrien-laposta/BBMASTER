#!/bin/bash

# Compute mode-coupling matrix
#python3 -m bbmaster.mcmer --globals=data/globals.yml --output-dir=mbatch_out/ --plot

# Filter all PL simulations and compute their power spectra (before and after filtering)
#for sim0 in 0 10 20 30 40 50 60 70 80 90
#do
#    echo ${sim0}
#    python3 -m bbmaster.filterer_mcut --globals=data/globals.yml --first-sim=${sim0} --num-sims=10 --sim-sorter=pl_sim_names --output-dir=mbatch_out/ --m-cut 30
#    python3 -m bbmaster.pcler --globals=data/globals.yml --first-sim=${sim0} --num-sims=10 --sim-sorter=pl_sim_names_EandB --output-dir=mbatch_out/ --sim-type=input
#    python3 -m bbmaster.pcler --globals=data/globals.yml --first-sim=${sim0} --num-sims=10 --sim-sorter=pl_sim_names_EandB --output-dir=mbatch_out/ --sim-type=filtered
#done

## Estimate transfer function
python3 -m bbmaster.transfer --globals=data/globals.yml --sim-sorter=pl_sim_names_EandB --output-dir=mbatch_out/ --use-theory --plot

## Validate transfer function
# Filter all validation sims, estimate their pseudo-C_ells before and after filtering, and their decoupled versions
for sim0 in 0 10 20 30 40 50 60 70 80 90
do
    echo ${sim0}
    #python3 -m bbmaster.filterer_mcut --globals=data/globals.yml --first-sim=${sim0} --num-sims=10 --sim-sorter=val_sim_names --output-dir=mbatch_out/ --m-cut 30
    #python3 -m bbmaster.pcler --globals=data/globals.yml --first-sim=${sim0} --num-sims=10 --sim-sorter=val_sim_names --output-dir=mbatch_out/ --sim-type=input
    #python3 -m bbmaster.pcler --globals=data/globals.yml --first-sim=${sim0} --num-sims=10 --sim-sorter=val_sim_names --output-dir=mbatch_out/ --sim-type=filtered
    #python3 -m bbmaster.pcler --globals=data/globals.yml --first-sim=${sim0} --num-sims=10 --sim-sorter=val_sim_names --output-dir=mbatch_out/ --sim-type=decoupled --mcm=mbatch_out/transfer.npz
done
