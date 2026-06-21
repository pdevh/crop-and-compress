import sys
import traceback

def main():
    try:
        import requests
        print("Import successful")
    except ImportError as e:
        print(f"ImportError: {e}")
    except Exception as e:
        print(f"Exception: {type(e).__name__}: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
