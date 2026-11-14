"""Biquad design (RBJ cookbook) and evaluation at the DSP's rate (config.DSP_FS, 48 kHz).

Standard form:  H(z) = (b0 + b1 z^-1 + b2 z^-2) / (1 + a1 z^-1 + a2 z^-2)
miniDSP form:   [b0, b1, b2, -a1, -a2]   (feedback terms sign-flipped)
"""
from __future__ import annotations

import numpy as np

from .config import DSP_FS


def peaking(fc, q, gain_db, fs=DSP_FS):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * fc / fs
    alpha = np.sin(w) / (2 * q)
    cw = np.cos(w)
    b = np.array([1 + alpha * A, -2 * cw, 1 - alpha * A])
    a = np.array([1 + alpha / A, -2 * cw, 1 - alpha / A])
    return b / a[0], a / a[0]


def lowshelf(fc, q, gain_db, fs=DSP_FS):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * fc / fs
    cw, sw = np.cos(w), np.sin(w)
    alpha = sw / (2 * q)
    k = 2 * np.sqrt(A) * alpha
    b = np.array([A * ((A + 1) - (A - 1) * cw + k), 2 * A * ((A - 1) - (A + 1) * cw),
                  A * ((A + 1) - (A - 1) * cw - k)])
    a = np.array([(A + 1) + (A - 1) * cw + k, -2 * ((A - 1) + (A + 1) * cw),
                  (A + 1) + (A - 1) * cw - k])
    return b / a[0], a / a[0]


def lowpass(fc, q=0.70710678, fs=DSP_FS):
    w = 2 * np.pi * fc / fs
    alpha = np.sin(w) / (2 * q)
    cw = np.cos(w)
    b = np.array([(1 - cw) / 2, 1 - cw, (1 - cw) / 2])
    a = np.array([1 + alpha, -2 * cw, 1 - alpha])
    return b / a[0], a / a[0]


def lr4_lowpass(fc):
    """Linkwitz-Riley 24 dB/oct = two cascaded Butterworth Q=0.707 sections."""
    return [lowpass(fc), lowpass(fc)]


def to_minidsp(b, a):
    return (float(b[0]), float(b[1]), float(b[2]), float(-a[1]), float(-a[2]))


def response(b, a, f, fs=DSP_FS):
    z1 = np.exp(-2j * np.pi * np.asarray(f) / fs)
    return (b[0] + b[1] * z1 + b[2] * z1 ** 2) / (1 + a[1] * z1 + a[2] * z1 ** 2)


def peq_chain_response(bands, f, fs=DSP_FS):
    """bands: iterable of (fc, q, gain_db) peaking filters."""
    h = np.ones(len(f), dtype=complex)
    for fc, q, g in bands:
        h *= response(*peaking(fc, q, g, fs), f, fs)
    return h
