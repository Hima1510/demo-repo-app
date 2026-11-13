"""Release switches used to simulate good/bad commits in demos.

Flip FAULTY_RELEASE to True and push to simulate a commit that breaks the
app: the test suite fails (test_release_is_healthy) and, if deployed anyway,
the app serves slow, failing responses.
"""

FAULTY_RELEASE = False
