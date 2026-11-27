"""C4 L3: Execution Event Listener — inbound AMQP adapter for queue `execution.events`.

OWNER: Member 2 (Runner Worker + Sandbox + RabbitMQ) — implemented in Phase 2/4.
The business side is DONE and tested; this module only has to wire AMQP to it.

What the listener must do for every message (docs/phase1/03 §1, M2 §3.3 steps 13-27):
  1. Parse the JSON body. Use field `type` to pick the model:
        app.core.messages.ExecutionHeartbeat  or  app.core.messages.ExecutionFinished
     A message that fails validation (T10) -> reject without requeue (goes to execution.events.dlq).
  2. Open a session:  session = app.core.database.session_factory()()
  3. Call the orchestrator (the ONLY status writer):
        orch = ExecutionOrchestrator(session, publisher, settings)
        orch.on_heartbeat(msg)   or   orch.on_finished(msg)
     Both commit internally and are idempotent (duplicates / late events are ignored).
  4. Ack the AMQP message only AFTER the call returns. On an exception: nack with requeue.
  5. Close the session.
"""
