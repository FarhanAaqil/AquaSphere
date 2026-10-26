"""
Unit and behavioural tests for Tier B Spatial Patch CNN model (SIH 26066).
"""

import torch

from aquasphere.models.patch_cnn import PatchCNNEncoder, TierBModel


def test_patch_cnn_encoder_forward() -> None:
    encoder = PatchCNNEncoder(in_channels=7, base_channels=32, embed_dim=32)
    x = torch.randn(8, 7, 9, 9)
    out = encoder(x)

    assert out.shape == (8, 32)
    assert torch.isfinite(out).all()


def test_tier_b_model_parameter_count_cap() -> None:
    model = TierBModel(
        in_channels=7,
        base_channels=32,
        scalar_dim=18,
        scalar_embed_dim=16,
        embed_dim=32,
        hidden_dim=128,
        n_depths=15,
    )
    n_params = model.count_parameters()
    # Hard cap <= 300,000 parameters to stay CPU trainable
    assert n_params <= 300_000
    assert n_params > 10_000


def test_tier_b_model_forward_and_unit_norm() -> None:
    model = TierBModel(
        in_channels=7,
        base_channels=16,
        scalar_dim=18,
        scalar_embed_dim=16,
        embed_dim=32,
        hidden_dim=64,
        normalize_embed=True,
    )
    patches = torch.randn(10, 7, 9, 9)
    scalars = torch.randn(10, 18)

    pred_mean, pred_log_sigma2, emb = model(patches, scalars)

    assert pred_mean.shape == (10, 15)
    assert pred_log_sigma2.shape == (10, 15)
    assert emb.shape == (10, 32)

    # L2 norm along embedding dimension must equal 1.0
    norms = torch.norm(emb, p=2, dim=-1)
    assert torch.allclose(norms, torch.ones_like(norms), atol=1e-5)


def test_tier_b_backward_gradients() -> None:
    model = TierBModel(
        in_channels=7,
        base_channels=16,
        scalar_dim=18,
        scalar_embed_dim=16,
        embed_dim=32,
        hidden_dim=64,
    )
    patches = torch.randn(4, 7, 9, 9)
    scalars = torch.randn(4, 18)

    pred_mean, pred_log_sigma2, _ = model(patches, scalars)
    loss = (pred_mean**2).mean() + pred_log_sigma2.mean()
    loss.backward()

    for name, p in model.named_parameters():
        assert p.grad is not None, f"Gradient missing for {name}"
        assert torch.isfinite(p.grad).all()
