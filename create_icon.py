from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

def create_red_black_s_icon():
    assets_dir = Path("assets")
    assets_dir.mkdir(exist_ok=True)
    
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    images = []

    for size_w, size_h in sizes:
        img = Image.new("RGBA", (size_w, size_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Background rounded rect (Black with Crimson Border)
        pad = max(1, int(size_w * 0.05))
        rect_coords = [pad, pad, size_w - pad, size_h - pad]
        corner_radius = max(2, int(size_w * 0.2))

        # Outer glow/border (Dark Crimson Red)
        draw.rounded_rectangle(rect_coords, radius=corner_radius, fill=(15, 10, 12, 255), outline=(211, 47, 47, 255), width=max(1, int(size_w * 0.06)))

        # Inner subtle gradient circle / accent shape
        inner_pad = max(2, int(size_w * 0.15))
        draw.ellipse([inner_pad, inner_pad, size_w - inner_pad, size_h - inner_pad], fill=(30, 10, 15, 180))

        # Stylized 'S' Text
        try:
            # Try to load a bold font or fallback to default
            font_size = int(size_w * 0.65)
            font = ImageFont.truetype("arialbd.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        text = "S"

        # Get text bbox to center it
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        x = (size_w - text_w) / 2 - bbox[0]
        y = (size_h - text_h) / 2 - bbox[1]

        # Draw red shadow / glow for letter S
        draw.text((x + 1, y + 1), text, fill=(139, 0, 0, 255), font=font)
        # Draw bright crimson letter S
        draw.text((x, y), text, fill=(255, 51, 68, 255), font=font)

        images.append(img)

    # Save multi-size ICO
    ico_path = assets_dir / "app_icon.ico"
    png_path = assets_dir / "app_icon.png"

    images[0].save(png_path, format="PNG")
    images[0].save(ico_path, format="ICO", sizes=sizes)
    print(f"Icon generated successfully at {ico_path}")

if __name__ == "__main__":
    create_red_black_s_icon()
