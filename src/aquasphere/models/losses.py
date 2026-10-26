"""
Loss functions for subsurface ocean temperature reconstruction (SIH 26066).

Implements:
1. Masked heteroscedastic NLL loss with thermocline depth weighting (wk=2.0 for 50-150m).
2. Clamped variance log_sigma2 to guarantee numerical stability.
3. Profile vertical gradient smoothness penalty (lambda_grad).
4. Physical temperature inversion penalty (lambda_phys).
5. Warmup mode (weighted masked MSE) for early training epochs.
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from aquasphere.constants import STANDARD_DEPTHS


class MaskedHeteroscedasticLoss(nn.Module):
    """Masked heteroscedastic NLL and physics-regularised loss."""

    def __init__(
        self,
        thermocline_weight: float = 2.0,
        lambda_grad: float = 0.01,
        lambda_phys: float = 0.001,
        eps_inv: float = 0.0,
        log_sigma2_min: float = -6.0,
        log_sigma2_max: float = 4.0,
    ) -> None:
        super().__init__()
        self.lambda_grad = lambda_grad
        self.lambda_phys = lambda_phys
        self.eps_inv = eps_inv
        self.log_sigma2_min = log_sigma2_min
        self.log_sigma2_max = log_sigma2_max

        # Construct depth weights: 2.0 for 50-150m, 1.0 for other depths
        thermo_depths = {50, 75, 100, 125, 150}
        weights = [thermocline_weight if d in thermo_depths else 1.0 for d in STANDARD_DEPTHS]
        self.register_buffer("depth_weights", torch.tensor(weights, dtype=torch.float32))

    def forward(
        self,
        pred_mean: torch.Tensor,
        pred_log_sigma2: torch.Tensor,
        target: torch.Tensor,
        mask: torch.Tensor | None = None,
        use_nll: bool = True,
    ) -> torch.Tensor:
        """Compute loss over batch.

        Args:
            pred_mean: [B, 15] predicted temperatures
            pred_log_sigma2: [B, 15] predicted log variance
            target: [B, 15] true temperatures
            mask: [B, 15] binary mask (1=observed, 0=unobserved). If None, inferred from ~isnan(target).
            use_nll: If False, uses weighted masked MSE (warm-up mode).
        """
        if mask is None:
            mask = (~torch.isnan(target)).float()
        else:
            mask = mask.float()

        # Fill any target NaNs with 0 to prevent gradient corruption (mask will zero them out)
        target_clean = torch.where(torch.isnan(target), torch.zeros_like(target), target)

        if target.shape[1] == self.depth_weights.shape[0]:
            weights = self.depth_weights.unsqueeze(0)
        else:
            weights = self.depth_weights[: target.shape[1]].unsqueeze(0)
        effective_weights = mask * weights

        diff = pred_mean - target_clean

        if not use_nll:
            # MSE warm-up mode
            sq_err = diff**2
            weighted_mse = (sq_err * effective_weights).sum() / (effective_weights.sum() + 1e-8)
            return weighted_mse

        # Heteroscedastic NLL mode: 0.5 * (diff^2 / sigma^2 + log_sigma^2)
        clamped_log_sigma2 = torch.clamp(
            pred_log_sigma2, min=self.log_sigma2_min, max=self.log_sigma2_max
        )
        inv_sigma2 = torch.exp(-clamped_log_sigma2)
        nll_per_element = 0.5 * (diff**2 * inv_sigma2 + clamped_log_sigma2)

        data_loss = (nll_per_element * effective_weights).sum() / (effective_weights.sum() + 1e-8)

        # Gradient smoothness: |Delta pred - Delta true| for adjacent observed depths
        grad_loss = torch.tensor(0.0, device=pred_mean.device)
        if self.lambda_grad > 0:
            delta_pred = pred_mean[:, 1:] - pred_mean[:, :-1]
            delta_target = target_clean[:, 1:] - target_clean[:, :-1]
            adjacent_mask = mask[:, 1:] * mask[:, :-1]
            grad_diff = torch.abs(delta_pred - delta_target)
            grad_loss = (grad_diff * adjacent_mask).sum() / (adjacent_mask.sum() + 1e-8)

        # Physical inversion penalty: ReLU(T_{k+1} - T_k - eps_inv)
        phys_loss = torch.tensor(0.0, device=pred_mean.device)
        if self.lambda_phys > 0:
            inversion = pred_mean[:, 1:] - pred_mean[:, :-1] - self.eps_inv
            inversion_penalty = F.relu(inversion)
            adjacent_mask = mask[:, 1:] * mask[:, :-1]
            phys_loss = (inversion_penalty * adjacent_mask).sum() / (adjacent_mask.sum() + 1e-8)

        total_loss = data_loss + self.lambda_grad * grad_loss + self.lambda_phys * phys_loss
        return total_loss
