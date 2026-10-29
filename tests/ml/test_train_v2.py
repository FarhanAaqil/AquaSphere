"""Protocol v2 profile models on a small synthetic table where SST and SLA drive the anomaly."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import torch

from aquasphere.constants import STANDARD_DEPTHS
from aquasphere.data.patches import CHANNELS as PATCH_CHANNELS
from aquasphere.data.patches import LAGS
from aquasphere.eval import baselines_v2 as b
from aquasphere.models.losses import MaskedHeteroscedasticLoss
from aquasphere.train import v2
from tests.unit.test_baselines_v2 import _table

N_D = len(STANDARD_DEPTHS)


def _float_ids(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["float_id"] = df["profile_id"].str.split("_").str[0]
    return df


@pytest.fixture(scope="module")
def data() -> tuple[pd.DataFrame, pd.DataFrame]:
    return _float_ids(_table(1200, 0)), _float_ids(_table(300, 1))


def _patches(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    p = rng.normal(size=(n, len(LAGS), len(PATCH_CHANNELS), 9, 9)).astype(np.float16)
    p[:, :, 2, :2] = np.nan  # some missing SSS pixels
    land = np.zeros((n, 9, 9), dtype=bool)
    land[:, 0, 0] = True
    return p, land


def _thermo(pred: np.ndarray, df: pd.DataFrame) -> float:
    y, mask = b.targets(df)
    idx = v2.THERMO
    err = np.where(mask[:, idx], pred[:, idx] - y[:, idx], 0.0)
    return float(np.sqrt((err**2).sum() / mask[:, idx].sum()))


def test_tier_a_learns_beats_climatology_and_round_trips(data: tuple) -> None:  # type: ignore[type-arg]
    train, val = data
    model = v2.ProfileModel(v2.Config(epochs=25, patience=25)).fit(train, seed=0)
    mean, sigma, emb = model.predict(val)
    assert mean.shape == sigma.shape == (len(val), N_D) and emb.shape == (len(val), 16)
    assert np.all(sigma > 0)
    assert np.allclose(np.linalg.norm(emb, axis=1), 1.0, atol=1e-5)
    clim = b.B0Climatology().fit(train).predict(val)
    assert _thermo(mean, val) < 0.9 * _thermo(clim, val)
    again = v2.ProfileModel.from_state(model.state())
    assert np.allclose(again.predict(val)[0], mean, atol=1e-5)
    assert again.train_floats == sorted(set(train["float_id"]))


def test_nowcast_mode_ignores_delayed_sensors(data: tuple) -> None:  # type: ignore[type-arg]
    train, val = data
    model = v2.ProfileModel(v2.Config(epochs=3)).fit(train, seed=0)
    shuffled = val.copy()
    for c in ("sss", "ug", "vg", "u10", "v10"):
        shuffled[c] = shuffled[c].sample(frac=1.0, random_state=0).to_numpy()
    a, _, _ = model.predict(val, mode="nowcast")
    c, _, _ = model.predict(shuffled, mode="nowcast")
    assert np.allclose(a, c)  # nowcast output cannot depend on wind, currents or salinity
    d, _, _ = model.predict(shuffled, mode="delayed")
    assert not np.allclose(a, d)
    with pytest.raises(ValueError):
        model.predict(val, mode="hindcast")


def test_ablation_channels_are_never_seen(data: tuple) -> None:  # type: ignore[type-arg]
    train, val = data
    model = v2.ProfileModel(v2.Config(epochs=2, channels=v2.ABLATION["A1"])).fit(train, seed=0)
    noisy = val.assign(sla=0.0)
    assert np.allclose(model.predict(val)[0], model.predict(noisy)[0])


def test_label_fraction_and_held_out_stop_floats(data: tuple) -> None:  # type: ignore[type-arg]
    train, _ = data
    full = v2.ProfileModel(v2.Config(epochs=2)).fit(train, seed=0)
    part = v2.ProfileModel(v2.Config(epochs=2, label_fraction=0.25)).fit(train, seed=0)
    n_floats = train["float_id"].nunique()
    n_stop = round(0.1 * n_floats)
    assert full.n_label_floats == n_floats - n_stop
    assert part.n_label_floats == round(0.25 * (n_floats - n_stop))
    # Short runs (epochs <= warmup) still return a selected, trained state
    assert len(part.history) == 2 and np.isfinite(part.stop_score)


def test_tier_b_and_c_with_pretrained_encoder(data: tuple) -> None:  # type: ignore[type-arg]
    train, val = data
    p_tr, l_tr = _patches(len(train), 0)
    p_va, l_va = _patches(len(val), 1)
    norm = v2.PatchNorm().fit(p_tr)
    tier_b = v2.ProfileModel(v2.Config(tier="B", epochs=2)).fit(
        train, seed=0, patches=p_tr, land=l_tr, patch_norm=norm
    )
    mean, _, emb = tier_b.predict(val, patches=p_va, land=l_va)
    assert mean.shape == (len(val), N_D) and emb.shape[1] == 32 and np.isfinite(mean).all()

    unl, unl_land = _patches(256, 2)
    for variant in ("masked", "masked+temporal"):
        enc, losses = v2.pretrain(unl, unl_land, norm, variant=variant, epochs=2, batch=64)
        assert len(losses) == 2 and all(np.isfinite(losses))
    frozen = {k: t.clone() for k, t in enc.state_dict().items()}
    tier_c = v2.ProfileModel(v2.Config(tier="C", epochs=2, freeze_epochs=5)).fit(
        train, seed=0, patches=p_tr, land=l_tr, patch_norm=norm, encoder=enc
    )
    # Still inside the frozen phase: the pre-trained encoder weights are untouched
    now = tier_c.model.net.patch_encoder.state_dict()
    assert all(
        torch.equal(frozen[k], now[k])
        for k in frozen
        if "running" not in k and "num_batches" not in k
    )
    again = v2.ProfileModel.from_state(tier_c.state())
    assert np.allclose(
        again.predict(val, patches=p_va, land=l_va)[0],
        tier_c.predict(val, patches=p_va, land=l_va)[0],
        atol=1e-5,
    )
    with pytest.raises(ValueError):
        v2.pretrain(unl, unl_land, norm, variant="contrastive")


def test_climatology_serialises_exactly(data: tuple) -> None:  # type: ignore[type-arg]
    train, val = data
    y, _ = b.targets(train)
    clim = b.Climatology().fit(train, y)
    again = b.Climatology.from_dict(clim.to_dict())
    assert np.allclose(again.predict(val), clim.predict(val), equal_nan=True)


def test_inversion_penalty_uses_absolute_temperature() -> None:
    loss = MaskedHeteroscedasticLoss(lambda_grad=0.0, lambda_phys=1.0)
    mean = torch.zeros(1, N_D)  # zero anomaly: absolute profile = climatology
    target = torch.zeros(1, N_D)
    log_s2 = torch.zeros(1, N_D)
    cooling = torch.linspace(28, 5, N_D).unsqueeze(0)
    warming = torch.linspace(5, 28, N_D).unsqueeze(0)
    base = loss(mean, log_s2, target, offset=None)
    assert torch.isclose(loss(mean, log_s2, target, offset=cooling), base)
    assert loss(mean, log_s2, target, offset=warming) > base + 1.0
