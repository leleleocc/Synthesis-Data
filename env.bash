export DAYTONA_API_KEY=dtn_2954aaddb1b77e1b886edf0fe9eebf3b7ec2489e7d05959ab474dc11ddea51dc
export ANTHROPIC_AUTH_TOKEN=sk-ts-7932674daf29a88f77ef0e52a46dd69968e77fea8d1fe9fc82f52de766d87ead
export ANTHROPIC_BASE_URL=https://true-sota.com
harbor run \
  -p Simula/tasks/v1-0922 \
  -a claude-code \
  -m grok-4.7 \
  -e daytona \
  --agent-kwarg 'reasoning_effort=max' \
  --agent-env 'CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0'
