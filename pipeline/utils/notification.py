from datetime import datetime


def notify_success(pipeline, message=""):

    print("\n" + "=" * 70)
    print(f"{pipeline} PIPELINE SUCCESS")
    print("=" * 70)

    if message:
        print(message)

    print(f"Completed : {datetime.now()}")
    print("=" * 70)


def notify_skipped(pipeline, reason=""):

    print("\n" + "=" * 70)
    print(f"{pipeline} PIPELINE SKIPPED")
    print("=" * 70)

    if reason:
        print(reason)

    print(f"Time : {datetime.now()}")
    print("=" * 70)


def notify_failed(pipeline, error):

    print("\n" + "=" * 70)
    print(f"{pipeline} PIPELINE FAILED")
    print("=" * 70)

    print(error)

    print(f"Time : {datetime.now()}")
    print("=" * 70)

    raise Exception(error)