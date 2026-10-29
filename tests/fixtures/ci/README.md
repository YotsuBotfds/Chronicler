# Historical standard Tests workflow

`standard-tests-cbf6e368.yml` is the byte-exact historical workflow at
`cbf6e368ebd218c1f54179bee4accffc1ab2a4c0`, SHA-256
`2dc117396d676801153d4458a12d9fdd0021b80268099b85e35f00b7b6b423b1`.
It preserves the old isolated prototype's migration/source contracts.

Current standard graph, gate names, failure barriers, full native delegation,
wheel transfer and trigger coverage read the real `.github/workflows/tests.yml`
in `test_native_build_lanes.py` and `test_native_wheel_receipt.py`. This fixture
does not stand in for the current workflow.
