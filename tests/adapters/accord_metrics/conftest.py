"""Fixtures for accord_metrics adapter tests.

2.9.7 (second-signer removal): the instance-hash / key-id derivations read
the persist Engine's local signer via get_persist_engine(). Tests run
without a wired engine, so the service exercises the fallback agent_id
hashing path; no signing mock is needed. (Trace SIGNING moved to the
lens-core substrate in the 2.9.6 fold — CIRISAgent#866.)
"""
