"""
Unit and behavioural tests for Tier C Self-Supervised Pre-Training (SIH 26066).
"""

import torch

from aquasphere.models.ssl import (
    MaskedPatchAutoencoder,
    PatchDecoder,
    TierCModel,
    generate_patch_mask,
)


def test_generate_patch_mask_strategies() -> None:
    # 1. Masked patch strategy
    m1 = generate_patch_mask(
        batch_size=4, channels=7, height=9, width=9, mask_ratio=0.50, strategy="masked_patch"
    )
    assert m1.shape == (4, 7, 9, 9)
    assert ((m1 == 0.0) | (m1 == 1.0)).all()
    # Mask ratio should be approximately 0.50
    ratio1 = m1.float().mean().item()
    assert 0.30 <= ratio1 <= 0.70

    # 2. Masked channel strategy
    m2 = generate_patch_mask(
        batch_size=4, channels=7, height=9, width=9, mask_ratio=0.50, strategy="masked_channel"
    )
    assert m2.shape == (4, 7, 9, 9)
    # Check that each channel is either fully masked or fully unmasked
    for b in range(4):
        for c in range(7):
            val = m2[b, c, 0, 0]
            assert (m2[b, c] == val).all()


def test_patch_decoder_forward() -> None:
    decoder = PatchDecoder(embed_dim=32, out_channels=7, base_channels=32)
    z = torch.randn(5, 32)
    out = decoder(z)

    assert out.shape == (5, 7, 9, 9)
    assert torch.isfinite(out).all()


def test_masked_patch_autoencoder_loss() -> None:
    autoencoder = MaskedPatchAutoencoder(
        in_channels=7, base_channels=16, embed_dim=32, mask_ratio=0.50, strategy="masked_patch"
    )
    x = torch.randn(6, 7, 9, 9)
    recon, mask = autoencoder(x)

    assert recon.shape == x.shape
    assert mask.shape == x.shape

    loss = autoencoder.compute_pretrain_loss(recon, x, mask)
    assert torch.isfinite(loss)
    assert loss.item() > 0.0

    loss.backward()
    for p in autoencoder.parameters():
        assert p.grad is not None
        assert torch.isfinite(p.grad).all()


def test_tier_c_fine_tuning_and_freeze() -> None:
    autoencoder = MaskedPatchAutoencoder(in_channels=7, base_channels=16, embed_dim=32)
    model = TierCModel(pretrained_encoder=autoencoder.encoder, embed_dim=32, hidden_dim=64)

    # Test freeze
    model.freeze_encoder(True)
    for p in model.patch_encoder.parameters():
        assert not p.requires_grad

    # Test unfreeze
    model.freeze_encoder(False)
    for p in model.patch_encoder.parameters():
        assert p.requires_grad

    patches = torch.randn(4, 7, 9, 9)
    scalars = torch.randn(4, 18)
    pred_mean, pred_log_sigma2, emb = model(patches, scalars)

    assert pred_mean.shape == (4, 15)
    assert pred_log_sigma2.shape == (4, 15)
    assert emb.shape == (4, 32)
