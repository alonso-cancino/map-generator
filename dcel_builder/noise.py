"""Spectral noise generation (FFT-based) for 2D/1D fields, plus deterministic seed derivation."""

from __future__ import annotations

import hashlib
import logging

import numpy as np

logger = logging.getLogger(__name__)


def derive_seed(master_seed: int, *components: str | int) -> int:
    """Derive a deterministic sub-seed from a master seed and component identifiers.

    Uses SHA-256 to produce independent, reproducible seeds for each component
    of the generation pipeline.
    """
    data = f"{master_seed}" + "".join(f":{c}" for c in components)
    digest = hashlib.sha256(data.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def spectral_noise_2d(resolution: int, exponent: float, seed: int) -> np.ndarray:
    """Generate a 2D spectral noise field via FFT synthesis.

    Args:
        resolution: Grid size (output is resolution x resolution).
        exponent: Power-law exponent beta controlling roughness.
        seed: RNG seed for reproducibility.

    Returns:
        2D array of shape (resolution, resolution), normalized to [0, 1].
    """
    logger.debug(
        "spectral_noise_2d: resolution=%d, exponent=%.2f, seed=%d", resolution, exponent, seed
    )
    rng = np.random.default_rng(seed % (2**63))
    n = resolution

    noise_real = rng.standard_normal((n, n))
    noise_imag = rng.standard_normal((n, n))
    Z = noise_real + 1j * noise_imag

    freq_x = np.fft.fftfreq(n)
    freq_y = np.fft.fftfreq(n)
    fx, fy = np.meshgrid(freq_x, freq_y)
    f = np.sqrt(fx**2 + fy**2)

    f[0, 0] = 1.0
    H = Z / f ** (exponent / 2)
    H[0, 0] = 0.0

    h = np.real(np.fft.ifft2(H))

    h_min, h_max = h.min(), h.max()
    h = (h - h_min) / (h_max - h_min) if h_max > h_min else np.zeros_like(h)

    return h


def spectral_noise_1d(length: int, exponent: float, seed: int) -> np.ndarray:
    """Generate a 1D spectral noise signal via FFT synthesis.

    Args:
        length: Number of samples.
        exponent: Power-law exponent beta.
        seed: RNG seed.

    Returns:
        1D array of given length, zero-mean.
    """
    rng = np.random.default_rng(seed % (2**63))
    n = length

    noise_real = rng.standard_normal(n)
    noise_imag = rng.standard_normal(n)
    Z = noise_real + 1j * noise_imag

    freq = np.fft.fftfreq(n)
    f = np.abs(freq)
    f[0] = 1.0
    H = Z / f ** (exponent / 2)
    H[0] = 0.0

    h = np.real(np.fft.ifft(H))
    h -= h.mean()

    return h
