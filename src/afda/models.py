"""Model factories shared by AFDA training and the submission inference.

Architectures are kept identical to src/baseline_inference.py so that a
checkpoint trained with these classes loads unchanged into the self-contained
submission ``inference.py`` (whose inlined copies must match name-for-name).
"""
from __future__ import annotations

import torch
from torch import nn


def build_stage1_model() -> nn.Module:
    """MViTv2-S with a 2-class (ORIGINAL / RERECORDED) head."""
    from torchvision.models.video import mvit_v2_s

    model = mvit_v2_s(weights=None)
    model.head[1] = nn.Linear(model.head[1].in_features, 2)
    return model


class Stage2Temporal(nn.Module):
    """BiGRU over per-frame ResNet18 features -> collision/entry frame + scene heads."""

    def __init__(self):
        super().__init__()
        self.r = nn.GRU(512, 192, 2, batch_first=True, bidirectional=True, dropout=0.15)
        self.tc = nn.Linear(384, 1)
        self.te = nn.Linear(384, 1)
        self.scene = nn.Sequential(nn.Linear(768, 192), nn.ReLU(), nn.Dropout(0.2), nn.Linear(192, 4))

    def forward(self, x):
        h, _ = self.r(x)
        collision_logits = self.tc(h).squeeze(-1)
        entry_logits = self.te(h).squeeze(-1)
        collision_index = collision_logits.argmax(1)
        entry_index = entry_logits.argmax(1)
        batch = torch.arange(len(h), device=h.device)
        scene_input = torch.cat([h[batch, collision_index], h[batch, entry_index]], 1)
        return collision_index, entry_index, self.scene(scene_input)


class Stage3MViT(nn.Module):
    """MViTv2-S backbone with accel(4) + steer(3) heads."""

    def __init__(self):
        super().__init__()
        from torchvision.models.video import mvit_v2_s

        self.backbone = mvit_v2_s(weights=None)
        dimension = self.backbone.head[1].in_features
        self.backbone.head = nn.Identity()
        self.accel = nn.Linear(dimension, 4)
        self.steer = nn.Linear(dimension, 3)

    def forward(self, x):
        features = self.backbone(x)
        return self.accel(features), self.steer(features)


def build_stage2_backbone() -> nn.Module:
    """ResNet18 feature extractor (fc removed); weights loaded separately."""
    from torchvision.models import resnet18

    backbone = resnet18(weights=None)
    backbone.fc = nn.Identity()
    return backbone
