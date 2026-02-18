from pathlib import Path

from PIL import Image


def split_goods(
    image_path: Path,
    output_dir: Path,
    rows: int = 2,
    cols: int = 7,
) -> None:
    image = Image.open(image_path)
    width, height = image.size

    cell_width = width // cols
    cell_height = height // rows

    output_dir.mkdir(parents=True, exist_ok=True)

    for row in range(rows):
        for col in range(cols):
            left = col * cell_width
            upper = row * cell_height
            right = (col + 1) * cell_width if col < cols - 1 else width
            lower = (row + 1) * cell_height if row < rows - 1 else height
            tile = image.crop((left, upper, right, lower))
            tile_name = f"tile_r{row + 1}_c{col + 1}.png"
            tile.save(output_dir / tile_name)


def main() -> None:
    image_path = Path("goods.png")
    output_dir = Path("goods_tiles")
    split_goods(image_path, output_dir)


if __name__ == "__main__":
    main()
