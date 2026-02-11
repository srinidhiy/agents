from langsmith import Client

client = Client()

run_id = "755b601c-b9a6-4e25-b0a2-a20078de8947"

client.update_run(run_id, status="aborted")