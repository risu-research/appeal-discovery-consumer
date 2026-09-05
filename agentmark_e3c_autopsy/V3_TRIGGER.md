# E3c No-Shift Autopsy v3 Trigger

This file exists only to trigger the repaired autopsy workflow after the preceding YAML-invalid packaging attempt. It changes no scientific code, protocol parameter, observer implementation, gate, or analysis rule.

The v3 association rule is fixed before this run: when R2 creates a second wait for the same entity through VERIFY after a decision MISS, the scientific decision monitor is selected as the observation with the earliest absolute monotonic deadline.
