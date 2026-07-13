from __future__ import annotations

import base64
import hashlib
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from support_app.config import APP_ROOT, DEFAULT_MODEL, IMAGE_OUTPUT_DIR, IMAGE_UPLOAD_DIR, ensure_runtime_dirs
from support_app.costs import aggregate_costs, estimate_cost
from support_app.guardrails import redact_text
from support_app.models import ImageArtifact, ImageInput, UsageCost
from support_app.openai_clients import make_openai_client

ALLOWED_IMAGE_MIME_TYPES = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}
IMAGE_OUTPUT_PATTERNS = [
    "create image",
    "create an image",
    "generate image",
    "generate an image",
    "draw",
    "make a picture",
    "make an image",
    "visual",
    "diagram",
    "illustration",
    "mockup",
    "poster",
    "infographic",
]


def image_feature_enabled() -> bool:
    return os.getenv("ENABLE_IMAGE_SUPPORT", "true").lower() == "true"


def image_output_enabled() -> bool:
    return os.getenv("ENABLE_IMAGE_OUTPUT", "true").lower() == "true"


def safe_file_name(file_name: str) -> str:
    base_name = Path(file_name.strip()).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base_name)
    cleaned = cleaned.lstrip(".")
    return cleaned[:120] or "uploaded_image"


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(APP_ROOT))
    except ValueError:
        return str(path)


def max_upload_bytes() -> int:
    try:
        megabytes = float(os.getenv("IMAGE_MAX_UPLOAD_MB", "8"))
    except ValueError:
        megabytes = 8
    return int(max(megabytes, 0.1) * 1024 * 1024)


def max_image_side() -> int:
    try:
        return int(os.getenv("IMAGE_MAX_SIDE_PX", "1600"))
    except ValueError:
        return 1600


def max_upload_count() -> int:
    try:
        return int(os.getenv("IMAGE_MAX_UPLOAD_COUNT", "3"))
    except ValueError:
        return 3


def normalize_mime_type(mime_type: str, image_format: str | None) -> str:
    if mime_type in ALLOWED_IMAGE_MIME_TYPES:
        return mime_type
    if image_format == "PNG":
        return "image/png"
    if image_format == "JPEG":
        return "image/jpeg"
    if image_format == "WEBP":
        return "image/webp"
    return mime_type or "application/octet-stream"


def sanitize_image_bytes(image_input: ImageInput) -> tuple[bytes, str, int, int, str | None]:
    if len(image_input.data) > max_upload_bytes():
        return b"", image_input.mime_type, 0, 0, "Image is larger than the configured upload limit."

    try:
        image = Image.open(BytesIO(image_input.data))
        image.load()
    except UnidentifiedImageError:
        return b"", image_input.mime_type, 0, 0, "Uploaded file is not a valid image."
    except OSError as exc:
        return b"", image_input.mime_type, 0, 0, f"Image could not be opened: {exc}"

    mime_type = normalize_mime_type(image_input.mime_type, image.format)
    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        return b"", mime_type, 0, 0, "Only PNG, JPG, JPEG, and WEBP images are supported."

    sanitized = ImageOps.exif_transpose(image)
    sanitized.thumbnail((max_image_side(), max_image_side()))

    image_format = ALLOWED_IMAGE_MIME_TYPES[mime_type]
    output = BytesIO()
    if image_format == "JPEG":
        sanitized = sanitized.convert("RGB")
        sanitized.save(output, format="JPEG", quality=85, optimize=True)
    elif image_format == "WEBP":
        sanitized.save(output, format="WEBP", quality=85, method=4)
    else:
        sanitized.save(output, format="PNG", optimize=True)

    width, height = sanitized.size
    return output.getvalue(), mime_type, width, height, None


def save_uploaded_images(image_inputs: list[ImageInput], run_id: str) -> list[ImageArtifact]:
    ensure_runtime_dirs()
    if not image_feature_enabled():
        return []

    run_dir = IMAGE_UPLOAD_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[ImageArtifact] = []

    upload_count = max_upload_count()
    for index, image_input in enumerate(image_inputs, start=1):
        if index > upload_count:
            artifacts.append(
                ImageArtifact(
                    file_name=safe_file_name(image_input.file_name),
                    mime_type=image_input.mime_type or "application/octet-stream",
                    size_bytes=len(image_input.data),
                    width=0,
                    height=0,
                    sha256=hashlib.sha256(image_input.data).hexdigest(),
                    storage_path="",
                    source_type="uploaded",
                    error=f"Image upload limit exceeded. Maximum supported images: {upload_count}.",
                )
            )
            continue
        sanitized_bytes, mime_type, width, height, error = sanitize_image_bytes(image_input)
        file_name = safe_file_name(image_input.file_name)
        suffix = Path(file_name).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            suffix = ".jpg" if mime_type == "image/jpeg" else ".png"
        storage_name = f"{index:02d}_{Path(file_name).stem[:80]}{suffix}"
        storage_path = run_dir / storage_name
        sha256 = hashlib.sha256(sanitized_bytes or image_input.data).hexdigest()

        if not error:
            storage_path.write_bytes(sanitized_bytes)

        artifacts.append(
            ImageArtifact(
                file_name=file_name,
                mime_type=mime_type,
                size_bytes=len(sanitized_bytes or image_input.data),
                width=width,
                height=height,
                sha256=sha256,
                storage_path=relative_path(storage_path) if not error else "",
                source_type="uploaded",
                error=error,
            )
        )
    return artifacts


def image_data_url(artifact: ImageArtifact) -> str | None:
    if not artifact.storage_path:
        return None
    path = APP_ROOT / artifact.storage_path
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{artifact.mime_type};base64,{encoded}"


def output_text_from_response(response: Any) -> str:
    direct_text = getattr(response, "output_text", None)
    if direct_text:
        return str(direct_text).strip()

    fragments: list[str] = []
    for output in getattr(response, "output", []) or []:
        for content in getattr(output, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                fragments.append(str(text))
    return "\n".join(fragments).strip()


def usage_cost_from_response(response: Any) -> UsageCost:
    usage = getattr(response, "usage", None)
    if usage is None:
        return UsageCost()

    prompt_tokens = int(
        getattr(usage, "input_tokens", 0)
        or getattr(usage, "prompt_tokens", 0)
        or 0
    )
    completion_tokens = int(
        getattr(usage, "output_tokens", 0)
        or getattr(usage, "completion_tokens", 0)
        or 0
    )
    return estimate_cost(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, serpapi_searches=0)


def analyze_uploaded_images(artifacts: list[ImageArtifact]) -> tuple[str, UsageCost]:
    analyzable = [artifact for artifact in artifacts if artifact.storage_path and not artifact.error]
    if not analyzable or not image_feature_enabled():
        return format_image_context(artifacts), UsageCost()

    client = make_openai_client()
    if client is None or not os.getenv("OPENAI_API_KEY"):
        for artifact in analyzable:
            artifact.error = "OPENAI_API_KEY is not configured, so image analysis was skipped."
        return format_image_context(artifacts), UsageCost()

    model = os.getenv("OPENAI_IMAGE_ANALYSIS_MODEL", DEFAULT_MODEL)
    costs: list[UsageCost] = []
    for artifact in analyzable:
        data_url = image_data_url(artifact)
        if not data_url:
            artifact.error = "Saved image could not be read for analysis."
            continue
        try:
            response = client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Analyze this customer-support image for an AI support crew. "
                                    "Extract visible text, product labels, errors, damage, diagrams, "
                                    "and support-relevant observations. Do not identify people. "
                                    "If uncertain, say uncertain. Return concise bullet points."
                                ),
                            },
                            {"type": "input_image", "image_url": data_url},
                        ],
                    }
                ],
            )
            artifact.analysis = redact_text(output_text_from_response(response))
            costs.append(usage_cost_from_response(response))
        except Exception as exc:
            artifact.error = f"Image analysis failed: {exc}"

    return format_image_context(artifacts), aggregate_costs(*costs) if costs else UsageCost()


def format_image_context(artifacts: list[ImageArtifact]) -> str:
    if not artifacts:
        return "No images were attached."

    sections: list[str] = []
    for index, artifact in enumerate(artifacts, start=1):
        details = [
            f"Image {index}: {artifact.file_name}",
            f"Type: {artifact.mime_type}",
            f"Size: {artifact.width}x{artifact.height}px, {artifact.size_bytes} bytes",
            f"SHA256: {artifact.sha256}",
        ]
        if artifact.analysis:
            details.append(f"Analysis:\n{artifact.analysis}")
        if artifact.error:
            details.append(f"Image warning:\n{artifact.error}")
        sections.append("\n".join(details))
    return "\n\n".join(sections)


def wants_image_output(query: str) -> bool:
    normalized = query.lower()
    return any(pattern in normalized for pattern in IMAGE_OUTPUT_PATTERNS)


def build_image_generation_prompt(query: str, final_answer: str, image_context: str) -> str:
    return (
        "Create a clean, professional customer-support visual for the user's request. "
        "Use a simple composition, readable labels, and no private information. "
        "Do not include brand logos unless they are explicitly present in the request.\n\n"
        f"User request:\n{query}\n\n"
        f"Support answer context:\n{final_answer[:1600]}\n\n"
        f"Uploaded image analysis:\n{image_context[:1600]}"
    )


def generated_image_artifact(
    run_id: str,
    image_bytes: bytes,
    prompt: str,
    model: str,
) -> ImageArtifact:
    ensure_runtime_dirs()
    output_path = IMAGE_OUTPUT_DIR / f"{run_id}.png"
    output_path.write_bytes(image_bytes)
    try:
        image = Image.open(BytesIO(image_bytes))
        image.load()
        width, height = image.size
    except OSError:
        width, height = 0, 0
    return ImageArtifact(
        file_name=f"{run_id}.png",
        mime_type="image/png",
        size_bytes=len(image_bytes),
        width=width,
        height=height,
        sha256=hashlib.sha256(image_bytes).hexdigest(),
        storage_path=relative_path(output_path),
        source_type="generated",
        prompt=prompt,
        analysis=f"Generated with {model}.",
    )


def generate_image_output(
    query: str,
    final_answer: str,
    image_context: str,
    run_id: str,
) -> tuple[list[ImageArtifact], UsageCost]:
    if not image_feature_enabled() or not image_output_enabled() or not wants_image_output(query):
        return [], UsageCost()

    model = os.getenv("OPENAI_IMAGE_GENERATION_MODEL", "gpt-image-1")
    prompt = build_image_generation_prompt(query, final_answer, image_context)
    client = make_openai_client()
    if client is None or not os.getenv("OPENAI_API_KEY"):
        return [
            ImageArtifact(
                file_name="",
                mime_type="image/png",
                size_bytes=0,
                width=0,
                height=0,
                sha256="",
                storage_path="",
                source_type="generated",
                prompt=prompt,
                error="OPENAI_API_KEY is not configured, so image generation was skipped.",
            )
        ], UsageCost()

    kwargs: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "size": os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"),
        "n": 1,
    }
    quality = os.getenv("OPENAI_IMAGE_QUALITY", "").strip()
    if quality:
        kwargs["quality"] = quality

    try:
        response = client.images.generate(**kwargs)
        first_image = response.data[0]
        b64_json = getattr(first_image, "b64_json", None)
        if not b64_json:
            return [
                ImageArtifact(
                    file_name="",
                    mime_type="image/png",
                    size_bytes=0,
                    width=0,
                    height=0,
                    sha256="",
                    storage_path=getattr(first_image, "url", "") or "",
                    source_type="generated",
                    prompt=prompt,
                    analysis=f"Generated with {model}.",
                )
            ], estimate_cost(0, 0, 0, image_generation_count=1)
        image_bytes = base64.b64decode(b64_json)
        return [generated_image_artifact(run_id, image_bytes, prompt, model)], estimate_cost(
            0,
            0,
            0,
            image_generation_count=1,
        )
    except Exception as exc:
        return [
            ImageArtifact(
                file_name="",
                mime_type="image/png",
                size_bytes=0,
                width=0,
                height=0,
                sha256="",
                storage_path="",
                source_type="generated",
                prompt=prompt,
                error=f"Image generation failed: {exc}",
            )
        ], UsageCost()
