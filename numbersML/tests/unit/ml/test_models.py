"""
Unit tests for ML models.

Tests:
- All three model architectures (simple, full, transformer)
- Forward pass shapes and gradients
- Weight initialization
- Model factory function
- Config handling
- Target value calculation
"""

import numpy as np
import pytest
import torch
import torch.nn as nn

from ml.config import ModelConfig, PipelineConfig, get_default_config
from ml.model import (
    CNNFeatureExtractor,
    CryptoTargetModel,
    CryptoTransformerModel,
    MultiHeadAttentionWithRoPE,
    ResidualBlock,
    RotaryEmbedding,
    SimpleMLPModel,
    SwiGLU,
    SwiGLUFeedForward,
    TransformerBlock,
    create_model,
)
from src.pipeline.target_value import batch_calculate, hanning_window


class TestModelConfig:
    """Test model configuration."""

    def test_default_config(self):
        config = get_default_config()
        assert config.model.hidden_dims == [512, 256, 128]
        assert config.model.dropout == 0.4  # Updated from 0.2 to 0.4 for better regularization
        assert config.model.attention_heads == 4
        assert config.seed == 42

    def test_small_config(self):
        config = ModelConfig(hidden_dims=[64, 32, 16], dropout=0.1, attention_heads=4)
        assert config.hidden_dims == [64, 32, 16]
        assert config.dropout == 0.1


class TestCreateModel:
    """Test model factory function."""

    @pytest.fixture
    def config(self):
        return ModelConfig(hidden_dims=[64, 32, 16], dropout=0.1, attention_heads=4)

    @pytest.fixture
    def input_tensor(self):
        return torch.randn(4, 10, 36)

    def test_create_simple(self, config):
        model = create_model(36, config, model_type="simple")
        assert isinstance(model, SimpleMLPModel)

    def test_create_full(self, config):
        model = create_model(36, config, model_type="full")
        assert isinstance(model, CryptoTargetModel)

    def test_create_transformer(self, config):
        model = create_model(36, config, model_type="transformer")
        assert isinstance(model, CryptoTransformerModel)

    def test_create_invalid(self, config):
        with pytest.raises(ValueError, match="Unknown model type"):
            create_model(36, config, model_type="invalid")


class TestSimpleMLPModel:
    """Test simple MLP baseline model."""

    @pytest.fixture
    def config(self):
        return ModelConfig(hidden_dims=[64, 32, 16], dropout=0.1)

    @pytest.fixture
    def model(self, config):
        return SimpleMLPModel(36, config)

    def test_forward_shape(self, model):
        x = torch.randn(4, 10, 36)
        out = model(x)
        assert out.shape == (4,)

    def test_single_sample(self, model):
        model.eval()
        x = torch.randn(1, 5, 36)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (1,)

    def test_gradient_flow(self, model):
        x = torch.randn(4, 10, 36)
        out = model(x)
        loss = out.sum()
        loss.backward()
        for name, param in model.named_parameters():
            if param.requires_grad:
                assert param.grad is not None, f"No gradient for {name}"

    def test_different_seq_lengths(self, model):
        for seq_len in [1, 5, 10, 50]:
            x = torch.randn(2, seq_len, 36)
            out = model(x)
            assert out.shape == (2,)


class TestCryptoTargetModel:
    """Test CNN + Attention model."""

    @pytest.fixture
    def config(self):
        return ModelConfig(hidden_dims=[64, 32, 16], dropout=0.1, attention_heads=4)

    @pytest.fixture
    def model(self, config):
        return CryptoTargetModel(36, config)

    def test_forward_shape(self, model):
        x = torch.randn(4, 10, 36)
        out = model(x)
        assert out.shape == (4,)

    def test_gradient_flow(self, model):
        x = torch.randn(4, 10, 36)
        out = model(x)
        loss = out.sum()
        loss.backward()
        for name, param in model.named_parameters():
            if param.requires_grad:
                assert param.grad is not None, f"No gradient for {name}"

    def test_no_attention(self):
        config = ModelConfig(hidden_dims=[64, 32, 16], use_attention=False)
        model = CryptoTargetModel(36, config)
        x = torch.randn(4, 10, 36)
        out = model(x)
        assert out.shape == (4,)

    def test_deterministic_eval(self, model):
        model.eval()
        x = torch.randn(4, 10, 36)
        with torch.no_grad():
            out1 = model(x)
            out2 = model(x)
        assert torch.allclose(out1, out2)


class TestCryptoTransformerModel:
    """Test Transformer model."""

    @pytest.fixture
    def config(self):
        return ModelConfig(hidden_dims=[64, 32, 16], dropout=0.1, attention_heads=4)

    @pytest.fixture
    def model(self, config):
        return CryptoTransformerModel(36, config)

    def test_forward_shape(self, model):
        x = torch.randn(4, 10, 36)
        out = model(x)
        assert out.shape == (4,)

    def test_gradient_flow(self, model):
        x = torch.randn(4, 10, 36)
        out = model(x)
        loss = out.sum()
        loss.backward()
        for name, param in model.named_parameters():
            if param.requires_grad:
                assert param.grad is not None, f"No gradient for {name}"

    def test_deterministic_eval(self, model):
        model.eval()
        x = torch.randn(4, 10, 36)
        with torch.no_grad():
            out1 = model(x)
            out2 = model(x)
        assert torch.allclose(out1, out2)

    def test_different_seq_lengths(self, model):
        for seq_len in [5, 10, 30, 100]:
            x = torch.randn(2, seq_len, 36)
            out = model(x)
            assert out.shape == (2,)


class TestModelComponents:
    """Test individual model components."""

    def test_swiglu(self):
        swiglu = SwiGLU()
        x = torch.randn(4, 64)
        out = swiglu(torch.cat([x, x], dim=-1))
        assert out.shape == (4, 64)

    def test_rotary_embedding(self):
        rope = RotaryEmbedding(dim=16, max_seq_len=64)
        x = torch.randn(4, 10, 16)
        cos, sin = rope(x)
        assert cos.shape == (10, 16)
        assert sin.shape == (10, 16)

    def test_residual_block(self):
        block = ResidualBlock(64, 32, dropout=0.1)
        x = torch.randn(4, 64)
        out = block(x)
        assert out.shape == (4, 32)

    def test_residual_block_same_dim(self):
        block = ResidualBlock(64, 64, dropout=0.1)
        x = torch.randn(4, 64)
        out = block(x)
        assert out.shape == (4, 64)

    def test_cnn_feature_extractor(self):
        cnn = CNNFeatureExtractor(in_channels=64, out_channels=32, kernel_sizes=[3, 5, 7])
        x = torch.randn(4, 10, 64)
        out = cnn(x)
        assert out.shape == (4, 10, 32)

    def test_multi_head_attention_rope(self):
        attn = MultiHeadAttentionWithRoPE(d_model=64, n_heads=4, dropout=0.1)
        x = torch.randn(4, 10, 64)
        out = attn(x)
        assert out.shape == (4, 10, 64)

    def test_swiglu_ffn(self):
        ffn = SwiGLUFeedForward(d_model=64, d_ff=128, dropout=0.1)
        x = torch.randn(4, 10, 64)
        out = ffn(x)
        assert out.shape == (4, 10, 64)

    def test_transformer_block(self):
        block = TransformerBlock(d_model=64, n_heads=4, d_ff=128, dropout=0.1)
        x = torch.randn(4, 10, 64)
        out = block(x)
        assert out.shape == (4, 10, 64)


class TestTargetValue:
    """Test target value calculation."""

    def test_hanning_window(self):
        w = hanning_window(100)
        assert len(w) == 100
        assert abs(w.sum() - 1.0) < 1e-6
        assert all(w >= 0)

    def test_hanning_window_small(self):
        w = hanning_window(1)
        assert len(w) == 1
        assert w[0] == 1.0

    def test_hanning_window_zero(self):
        w = hanning_window(0)
        assert len(w) == 1
        assert w[0] == 1.0

    def test_batch_calculate(self):
        prices = list(range(100, 200))
        targets = batch_calculate(prices, window_size=10)
        assert len(targets) == len(prices)

    def test_batch_calculate_constant(self):
        """Constant prices return zero (deviation from trend)."""
        prices = [100.0] * 50
        targets = batch_calculate(prices, window_size=10)
        assert len(targets) == 50
        # Target is deviation from smoothed trend, so 0 for constant prices
        assert all(abs(t) < 0.1 for t in targets)

    def test_batch_calculate_empty(self):
        targets = batch_calculate([], window_size=10)
        assert targets == []

    def test_batch_calculate_single(self):
        """Single price returns 0 (no history)."""
        targets = batch_calculate([42.0], window_size=10)
        assert len(targets) == 1
        assert abs(targets[0]) < 1e-6

    def test_target_is_smoothed(self):
        # Create a price series with a spike
        prices = [100.0] * 50 + [200.0] + [100.0] * 50
        targets = batch_calculate(prices, window_size=20, use_kalman=False)
        # The spike at index 50 should be smoothed (target = 200 - smoothed ~100)
        assert abs(targets[50] - 100.0) < 50.0  # Should be around 100, not 200


class TestWeightInit:
    """Test weight initialization."""

    def test_no_nan_weights(self):
        config = ModelConfig(hidden_dims=[64, 32, 16])
        for model_type in ["simple", "full", "transformer"]:
            model = create_model(36, config, model_type)
            for name, param in model.named_parameters():
                assert not torch.isnan(param).any(), f"NaN in {model_type}/{name}"

    def test_no_inf_weights(self):
        config = ModelConfig(hidden_dims=[64, 32, 16])
        for model_type in ["simple", "full", "transformer"]:
            model = create_model(36, config, model_type)
            for name, param in model.named_parameters():
                assert not torch.isinf(param).any(), f"Inf in {model_type}/{name}"

    def test_weights_not_zero(self):
        config = ModelConfig(hidden_dims=[64, 32, 16])
        model = create_model(36, config, "simple")
        # At least some weights should be non-zero
        has_nonzero = False
        for param in model.parameters():
            if param.dim() >= 2 and (param != 0).any():
                has_nonzero = True
                break
        assert has_nonzero


class TestModelComparison:
    """Test relative model behavior."""

    @pytest.fixture
    def config(self):
        return ModelConfig(hidden_dims=[64, 32, 16], dropout=0.0, attention_heads=4)

    def test_all_models_same_output_shape(self, config):
        x = torch.randn(4, 10, 36)
        for model_type in ["simple", "full", "transformer"]:
            model = create_model(36, config, model_type)
            model.eval()
            with torch.no_grad():
                out = model(x)
            assert out.shape == (4,), f"{model_type} output shape mismatch"

    def test_transformer_has_most_params(self, config):
        params = {}
        for model_type in ["simple", "full", "transformer"]:
            model = create_model(36, config, model_type)
            params[model_type] = sum(p.numel() for p in model.parameters())
        assert params["simple"] < params["full"] < params["transformer"]

    def test_models_trainable(self, config):
        x = torch.randn(4, 10, 36)
        y = torch.randn(4)
        for model_type in ["simple", "full", "transformer"]:
            model = create_model(36, config, model_type)
            optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
            criterion = nn.MSELoss()

            # One training step
            model.train()
            optimizer.zero_grad()
            pred = model(x)
            loss = criterion(pred, y)
            loss.backward()
            optimizer.step()

            assert loss.item() > 0, f"{model_type} loss should be positive"
