"""Host-side CLI for the AIO Sandbox scaffold.

    sandbox/aio/sbx.sh <command> ...

Everything the host does lives here: configuring the veFaaS application's mount
points, publishing the runner and tenant templates to TOS, creating one sandbox
per task, and reading back what it left behind.

Nothing in this package ever runs inside a sandbox. That split is the credential
boundary: the Volcengine AK/SK stay here and the instance is never given a role
that could reach the API, which is what makes running an unsupervised agent
inside it an acceptable trade (see TODO.md sections 3 and 8).
"""
