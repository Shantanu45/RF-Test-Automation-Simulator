from rf_test_sim.config import RunConfig
from rf_test_sim.domain import Observation, PointResult, Verdict, evaluate

"""
Converts instrument readings into gain, signal-to-noise ratio (SNR), and a pass/fail decision for one measurement points.
This function performs calculations only; it does not communicate with instruments.
args:
    point_id: the point’s position in the sweep.
    observation: readings returned by the bench.
    config: cable losses and acceptance limits.
"""


def calculate(
    point_id: int, observation: Observation, config: RunConfig
) -> PointResult:
    # Generator → Input cable → DUT → Output cable → (carrier is measured here)Analyze
    carrier = (
        observation.carrier_dbm
    )  # A carrier is the main RF signal—the signal you want to generate, amplify, and measure
    # The cable between the generator and DUT reduces the signal power:
    # DUT input = generator power − input cable loss
    dut_input = observation.generator_power_dbm - config.model.input_loss_db
    # The output cable also loses power before the signal reaches the analyzer:
    # DUT output = analyzer carrier + output cable loss, carrier is measured after the output cable has already reduced the power. We add the loss back to estimate the power at the DUT output.
    dut_output = carrier + config.model.output_loss_db if carrier is not None else None
    # Subtracting two powers expressed in dBm produces a power ratio expressed in dB. A gain of 20 dB corresponds to 100 times the power
    gain = dut_output - dut_input if dut_output is not None else None
    # SNR compares the wanted signal with the measured noise
    snr = carrier - observation.noise_dbm if carrier is not None else None
    # It compares each value against its configured limits and returns a LimitResult, including the verdict and margin.
    # Limits can include a guard band, which makes the acceptance range stricter. For example, a 0.2 dB guard band changes an allowed gain range of 19–21 dB into 19.2–20.8 dB. Boundaries are inclusive.
    limits = (
        evaluate("gain", gain, config.gain_limit),
        evaluate("snr", snr, config.snr_limit),
    )
    verdict = Verdict.PASS
    if any(limit.verdict == Verdict.NOT_EVALUATED for limit in limits):
        verdict = Verdict.NOT_EVALUATED
    elif any(limit.verdict == Verdict.FAIL for limit in limits):
        verdict = Verdict.FAIL
    # Return everything as a PointResult
    return PointResult(
        point_id=point_id,
        frequency_hz=observation.frequency_hz,
        generator_power_dbm=observation.generator_power_dbm,
        bandwidth_hz=observation.bandwidth_hz,
        dut_input_dbm=dut_input,
        analyzer_carrier_dbm=carrier,
        analyzer_noise_dbm=observation.noise_dbm,
        dut_output_dbm=dut_output,
        gain_db=gain,
        snr_db=snr,
        limits=limits,
        verdict=verdict,
        unavailable_reason=observation.unavailable_reason,
    )
