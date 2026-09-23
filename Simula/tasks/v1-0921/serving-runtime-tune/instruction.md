The serving process started through /usr/local/bin/vllm-nonroot-entrypoint.sh will not honor a GPU memory cap once its identity is dropped. A live worker launched from that path still reserves almost the entire device, and a worker that is no longer root does not come back under the cap on its own. Success is one process, started from that launcher, that is both non-root and capped.

After the launcher is in that state, start the serve worker through /usr/local/bin/vllm-nonroot-entrypoint.sh and leave it running. Do not pull model weights or other artifacts from the network; only files already on the machine may be used. The worker must listen on a TCP port. Write /workspace/runtime_metrics.json as a single JSON object that reports that live process. The object must contain all of the following fields, and both constraints have to be true in the dump and on the running worker:

"entrypoint" is the string "/usr/local/bin/vllm-nonroot-entrypoint.sh".
"gpu_memory_utilization" is a JSON number, the watermark actually in force on the worker, strictly greater than 0 and at most 0.90.
"process_uid" is a JSON integer, the UID of the live serve worker, and it must not be 0.
"pid" is a JSON integer greater than 1 for that worker.
"listen_port" is a JSON integer for the TCP port the worker is bound to.
"ready" is JSON true only when that worker is alive and listening.

A dump that shows a watermark in (0, 0.90] while the matching process still runs as UID 0 is not complete. A dump that shows a non-zero UID while the matching process still runs above 0.90 is not complete. The file is not a kernel table and not an OpenAI-style completions report; it is the runtime metrics dump plus the identity of the live process.

You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
