from backend.app2 import app, process_due_messages


def run_once():
    with app.app_context():
        result = process_due_messages()
    print(
        f"[*] process_jobs completed: checked={result['checked']}, claimed={result['claimed']}",
        flush=True,
    )


if __name__ == "__main__":
    run_once()
