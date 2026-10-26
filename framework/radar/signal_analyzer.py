"""Signal processing and analysis for mmWave radar data.

Implements Range-FFT, Doppler-FFT, Range-Doppler map computation, SNR
measurement, target detection, and signal-quality validation routines
used during radar firmware verification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DetectedTarget:
    """A target detected in the range profile.

    Attributes:
        range_bin: FFT bin index of the detection.
        range_m: Estimated range in metres (if config provides range resolution).
        power_db: Detection power relative to noise floor in dB.
        velocity_mps: Estimated velocity in m/s (populated after Doppler processing).
    """

    range_bin: int
    range_m: float = 0.0
    power_db: float = 0.0
    velocity_mps: float = 0.0


class SignalAnalyzer:
    """Radar signal processing and quality analysis.

    All methods operate on numpy arrays produced by :class:`DataCapture`.

    Args:
        config: Radar configuration dictionary.  Expected keys include
                ``adc_samples``, ``num_chirps``, ``sample_rate_ksps``,
                ``freq_slope_mhz_per_us``, ``start_freq_ghz``,
                ``frame_periodicity_ms``, and ``num_rx``.
    """

    SPEED_OF_LIGHT: float = 3.0e8  # m/s

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config: Dict[str, Any] = config
        self._adc_samples: int = int(config.get("adc_samples", 256))
        self._num_chirps: int = int(config.get("num_chirps", 128))
        self._sample_rate_hz: float = float(config.get("sample_rate_ksps", 5000)) * 1e3
        self._freq_slope: float = float(config.get("freq_slope_mhz_per_us", 70)) * 1e12  # Hz/s
        self._start_freq: float = float(config.get("start_freq_ghz", 77)) * 1e9
        self._lambda: float = self.SPEED_OF_LIGHT / self._start_freq

        # Derived
        self._range_res: float = self.SPEED_OF_LIGHT / (2 * self._freq_slope * (self._adc_samples / self._sample_rate_hz))
        logger.debug("Range resolution: %.3f m", self._range_res)

    # -- FFT processing -------------------------------------------------------

    def compute_range_fft(self, adc_data: np.ndarray) -> np.ndarray:
        """Compute the range FFT for each chirp / virtual channel.

        Applies a Hanning window before the FFT.

        Args:
            adc_data: Complex ADC array, shape ``(num_chirps, num_virt_channels, adc_samples)``
                      or ``(num_chirps, adc_samples)`` for a single channel.

        Returns:
            Range FFT result with the same leading dimensions.
        """
        window = np.hanning(adc_data.shape[-1]).astype(np.float32)
        windowed = adc_data * window
        range_fft = np.fft.fft(windowed, axis=-1)
        logger.debug("Range FFT computed: shape=%s", range_fft.shape)
        return range_fft

    def compute_doppler_fft(self, range_data: np.ndarray) -> np.ndarray:
        """Compute the Doppler FFT across chirps for each range bin.

        Args:
            range_data: Range-FFT output, shape ``(num_chirps, ..., range_bins)``.

        Returns:
            Doppler-FFT result with axes ``(doppler_bins, ..., range_bins)``.
        """
        window = np.hanning(range_data.shape[0]).astype(np.float32)
        # Broadcast window along chirp axis
        shape = [1] * range_data.ndim
        shape[0] = range_data.shape[0]
        windowed = range_data * window.reshape(shape)
        doppler_fft = np.fft.fftshift(np.fft.fft(windowed, axis=0), axes=0)
        logger.debug("Doppler FFT computed: shape=%s", doppler_fft.shape)
        return doppler_fft

    def compute_range_doppler_map(self, frame_data: np.ndarray) -> np.ndarray:
        """Compute a 2-D Range-Doppler map (magnitude in dB).

        If *frame_data* has a virtual-channel dimension, the channels are
        averaged (non-coherently) after magnitude computation.

        Args:
            frame_data: Raw ADC frame, shape ``(num_chirps, [num_virt_ch,] adc_samples)``.

        Returns:
            2-D array (doppler_bins x range_bins) in dB scale.
        """
        range_fft = self.compute_range_fft(frame_data)
        doppler_fft = self.compute_doppler_fft(range_fft)
        mag = np.abs(doppler_fft)
        if mag.ndim == 3:
            mag = np.mean(mag, axis=1)  # average virtual channels
        rd_map_db = 20.0 * np.log10(mag + 1e-12)
        logger.debug("Range-Doppler map: shape=%s, dynamic range=%.1f dB",
                      rd_map_db.shape, float(np.ptp(rd_map_db)))
        return rd_map_db

    # -- measurements ---------------------------------------------------------

    def measure_snr(self, fft_data: np.ndarray, target_bin: int) -> float:
        """Measure signal-to-noise ratio at a given range/Doppler bin.

        The noise floor is estimated from the median of all bins excluding
        a guard window around the target.

        Args:
            fft_data: 1-D magnitude spectrum (linear scale).
            target_bin: Bin index of the target.

        Returns:
            SNR in dB.
        """
        mag = np.abs(fft_data)
        signal_power = float(mag[target_bin] ** 2)
        guard = max(3, len(mag) // 20)
        noise_bins = np.concatenate([
            mag[: max(0, target_bin - guard)],
            mag[target_bin + guard + 1:],
        ])
        noise_power = float(np.median(noise_bins) ** 2) if noise_bins.size > 0 else 1e-20
        snr_db = 10.0 * np.log10(signal_power / noise_power + 1e-20)
        logger.debug("SNR at bin %d: %.2f dB", target_bin, snr_db)
        return float(snr_db)

    def measure_signal_bandwidth(self, spectrum: np.ndarray) -> float:
        """Estimate the -3 dB bandwidth of a spectral peak.

        Args:
            spectrum: 1-D power spectrum in linear scale.

        Returns:
            Bandwidth in number of bins.  Multiply by frequency resolution
            to convert to Hz.
        """
        mag = np.abs(spectrum)
        peak_val = np.max(mag)
        threshold = peak_val / np.sqrt(2.0)  # -3 dB
        above = np.where(mag >= threshold)[0]
        if len(above) == 0:
            return 0.0
        bw_bins = float(above[-1] - above[0])
        logger.debug("Signal bandwidth: %.1f bins (-3 dB)", bw_bins)
        return bw_bins

    def detect_targets(
        self,
        range_profile: np.ndarray,
        threshold: float = 15.0,
    ) -> List[DetectedTarget]:
        """Detect targets in a 1-D range profile using CFAR-like thresholding.

        Args:
            range_profile: 1-D complex or magnitude range-FFT output.
            threshold: Detection threshold in dB above noise floor.

        Returns:
            List of :class:`DetectedTarget` instances.
        """
        mag = np.abs(range_profile)
        noise_floor = self.calculate_noise_floor(mag)
        threshold_linear = noise_floor * (10.0 ** (threshold / 20.0))

        peaks: List[DetectedTarget] = []
        for i in range(1, len(mag) - 1):
            if mag[i] > threshold_linear and mag[i] > mag[i - 1] and mag[i] > mag[i + 1]:
                power_db = 20.0 * np.log10(mag[i] / (noise_floor + 1e-20))
                peaks.append(DetectedTarget(
                    range_bin=i,
                    range_m=i * self._range_res,
                    power_db=float(power_db),
                ))
        logger.info("Detected %d target(s) above %.1f dB threshold", len(peaks), threshold)
        return peaks

    def calculate_noise_floor(self, spectrum: np.ndarray) -> float:
        """Estimate the noise floor from a spectrum.

        Uses the median of the magnitude values, which is robust to the
        presence of strong targets.

        Args:
            spectrum: 1-D magnitude array (linear scale).

        Returns:
            Noise floor estimate (linear scale).
        """
        mag = np.abs(spectrum)
        nf = float(np.median(mag))
        logger.debug("Noise floor estimate: %.4e (%.2f dB)", nf, 20 * np.log10(nf + 1e-20))
        return nf

    # -- quality gate ---------------------------------------------------------

    def validate_signal_quality(
        self,
        frame_data: np.ndarray,
        specs: Dict[str, float],
    ) -> Tuple[bool, Dict[str, Any]]:
        """Run a full signal-quality assessment against specifications.

        Args:
            frame_data: Raw ADC frame array.
            specs: Dictionary of quality thresholds.  Supported keys:
                   ``min_snr_db``, ``max_noise_floor_db``,
                   ``min_bandwidth_bins``.

        Returns:
            Tuple of (pass_flag, metrics_dict).
        """
        range_fft = self.compute_range_fft(frame_data)
        # Use first chirp / first channel for profile analysis
        profile = range_fft[0] if range_fft.ndim >= 2 else range_fft
        if profile.ndim >= 2:
            profile = profile[0]

        mag = np.abs(profile)
        peak_bin = int(np.argmax(mag))

        snr = self.measure_snr(profile, peak_bin)
        nf_linear = self.calculate_noise_floor(mag)
        nf_db = 20.0 * np.log10(nf_linear + 1e-20)
        bw = self.measure_signal_bandwidth(profile)

        metrics: Dict[str, Any] = {
            "snr_db": snr,
            "noise_floor_db": nf_db,
            "bandwidth_bins": bw,
            "peak_bin": peak_bin,
        }

        passed = True
        if "min_snr_db" in specs and snr < specs["min_snr_db"]:
            passed = False
            logger.warning("SNR %.2f dB below minimum %.2f dB", snr, specs["min_snr_db"])
        if "max_noise_floor_db" in specs and nf_db > specs["max_noise_floor_db"]:
            passed = False
            logger.warning("Noise floor %.2f dB above maximum %.2f dB", nf_db, specs["max_noise_floor_db"])
        if "min_bandwidth_bins" in specs and bw < specs["min_bandwidth_bins"]:
            passed = False
            logger.warning("Bandwidth %.1f bins below minimum %.1f", bw, specs["min_bandwidth_bins"])

        logger.info("Signal quality: %s  metrics=%s", "PASS" if passed else "FAIL", metrics)
        return passed, metrics
