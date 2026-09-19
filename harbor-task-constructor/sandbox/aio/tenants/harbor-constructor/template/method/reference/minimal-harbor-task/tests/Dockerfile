FROM python:3.11-slim

# Harbor hard-sets skip_tests_upload=True when
# [verifier].environment_mode = "separate", so the verifier image must own
# /tests itself — nothing is uploaded into the container at run time.
# The build context is this Dockerfile's own parent directory (tests/), not the
# task root, because harbor hands the Dockerfile path to Daytona's
# Image.from_dockerfile, which resolves every COPY source against that parent.
WORKDIR /tests

COPY . /tests
RUN chmod +x /tests/test.sh

# Install Reward Kit for criterion evaluation.
RUN pip install --no-cache-dir reward-kit

CMD ["/tests/test.sh"]
