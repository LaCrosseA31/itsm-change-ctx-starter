# rules/

Reserved for externalised policy.

In this teaching artifact every rule is a Python function in `agent/rules.py`.
In production, the same rules would live here as Rego policies evaluated by
[Open Policy Agent](https://www.openpolicyagent.org/) — that way the CAB and
compliance officers can co-own the policy file without touching Python.

The contract stays the same: each rule takes the gathered facts (RFC + service
+ downstream + history) and returns a structured result the harness reads.
