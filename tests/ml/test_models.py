"""
Unit and behavioural tests for Tier A models and masked heteroscedastic loss (SIH 26066).
"""

import torch

from aquasphere.models.decoder import TierAModel
from aquasphere.models.encoder import ResidualBlock, TierAEncoder
from aquasphere.models.losses import MaskedHeteroscedasticLoss


def test_residual_block_shape():
    block = ResidualBlock(dim=64)
    x = torch.randn(16, 64)
    out = block(x)
    assert out.shape == (16, 64)


def test_tier_a_encoder_unit_norm():
    encoder = TierAEncoder(input_dim=18, hidden_dim=64, embed_dim=16, normalize_embed=True)
    x = torch.randn(32, 18)
    emb = encoder(x)

    assert emb.shape == (32, 16)
    # Norm along embedding dimension must equal 1.0
    norms = torch.norm(emb, p=2, dim=-1)
    assert torch.allclose(norms, torch.ones_like(norms), atol=1e-5)


def test_tier_a_model_forward_shapes():
    model = TierAModel(input_dim=18, hidden_dim=64, embed_dim=16, n_depths=15)
    x = torch.randn(20, 18)
    pred_mean, pred_log_sigma2, emb = model(x)

    assert pred_mean.shape == (20, 15)
    assert pred_log_sigma2.shape == (20, 15)
    assert emb.shape == (20, 16)


def test_masked_heteroscedastic_loss_warmup():
    loss_fn = MaskedHeteroscedasticLoss(thermocline_weight=2.0)
    pred_mean = torch.tensor([[25.0, 20.0], [25.0, 20.0]])
    log_sigma2 = torch.zeros_like(pred_mean)
    target = torch.tensor([[24.0, 20.0], [25.0, 18.0]])
    mask = torch.tensor([[1.0, 1.0], [1.0, 0.0]])

    # In warmup mode (MSE), target[1, 1] is masked out
    loss_val = loss_fn(pred_mean, log_sigma2, target, mask=mask, use_nll=False)
    assert torch.isfinite(loss_val)
    assert loss_val.item() > 0.0


def test_masked_heteroscedastic_loss_backward_gradients():
    model = TierAModel(input_dim=18, hidden_dim=64, embed_dim=16, n_depths=15)
    loss_fn = MaskedHeteroscedasticLoss(thermocline_weight=2.0, lambda_grad=0.01, lambda_phys=0.001)

    x = torch.randn(10, 18)
    target = torch.randn(10, 15) * 5.0 + 20.0
    mask = torch.randint(0, 2, (10, 15)).float()
    mask[:, 0] = 1.0  # at least surface observed

    pred_mean, pred_log_sigma2, _ = model(x)
    loss = loss_fn(pred_mean, pred_log_sigma2, target, mask=mask, use_nll=True)

    assert torch.isfinite(loss)
    loss.backward()

    # All model parameters should receive finite gradients
    for p in model.parameters():
        assert p.grad is not None
        assert torch.all(torch.isfinite(p.grad))


def test_model_determinism_given_seed():
    torch.manual_seed(42)
    m1 = TierAModel(input_dim=18, hidden_dim=64, embed_dim=16)
    x = torch.randn(5, 18)

    torch.manual_seed(42)
    m2 = TierAModel(input_dim=18, hidden_dim=64, embed_dim=16)

    m1.eval()
    m2.eval()
    with torch.no_grad():
        out1, _, _ = m1(x)
        out2, _, _ = m2(x)

    assert torch.allclose(out1, out2)
