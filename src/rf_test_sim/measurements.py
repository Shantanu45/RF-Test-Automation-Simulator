from rf_test_sim.config import RunConfig
from rf_test_sim.domain import Observation, PointResult, Verdict, evaluate


def calculate(point_id: int, observation: Observation, config: RunConfig) -> PointResult:
    carrier = observation.carrier_dbm
    dut_input = observation.generator_power_dbm - config.model.input_loss_db
    dut_output = carrier + config.model.output_loss_db if carrier is not None else None
    gain = dut_output - dut_input if dut_output is not None else None
    snr = carrier - observation.noise_dbm if carrier is not None else None
    limits = (evaluate("gain", gain, config.gain_limit), evaluate("snr", snr, config.snr_limit))
    verdict = Verdict.PASS
    if any(limit.verdict == Verdict.NOT_EVALUATED for limit in limits):
        verdict = Verdict.NOT_EVALUATED
    elif any(limit.verdict == Verdict.FAIL for limit in limits):
        verdict = Verdict.FAIL
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
