from pathlib import Path
import pandas as pd


ROOT = Path("source_friend_v1/SIH26009_DATA")


def inspect_csv(path: Path):
    try:
        df = pd.read_csv(path)

        print("=" * 90)
        print(f"FILE: {path}")
        print("=" * 90)

        print(f"Rows       : {len(df)}")
        print(f"Columns    : {len(df.columns)}")
        print()

        print("Columns:")
        for column in df.columns:
            dtype = str(df[column].dtype)

            missing = (
                df[column].isna().mean() * 100
            )

            unique = df[column].nunique(
                dropna=True
            )

            print(
                f"  {column:<35}"
                f"{dtype:<15}"
                f"missing={missing:>6.2f}% "
                f"unique={unique}"
            )

        print()

        print("Sample:")
        print(
            df.head(3).to_string(
                index=False
            )
        )

        print()

    except Exception as exc:
        print("=" * 90)
        print(f"FILE: {path}")
        print("ERROR:", exc)
        print("=" * 90)


def main():

    if not ROOT.exists():
        raise FileNotFoundError(
            f"Dataset directory not found: {ROOT}"
        )

    files = sorted(
        ROOT.rglob("*.csv")
    )

    print()
    print("=" * 90)
    print("AYASK DATASET INVENTORY")
    print("=" * 90)
    print(f"Dataset root : {ROOT}")
    print(f"CSV files    : {len(files)}")
    print("=" * 90)
    print()

    for path in files:
        inspect_csv(path)


if __name__ == "__main__":
    main()