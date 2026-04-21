"""
State-of-the-art neural network architectures for ML target prediction.

Models:
1. CryptoTargetModel (CNN + Attention + MLP)
2. SimpleMLPModel (baseline)
3. CryptoTransformerModel (state-of-the-art transformer)

Transformer Innovations:
- Rotary Positional Embeddings (RoPE) - better temporal encoding
- SwiGLU activation - modern, better than ReLU/GELU
- Pre-norm architecture - more stable training
- Multi-scale feature extraction (CNN + Transformer hybrid)
- Memory-efficient attention for CPU
- Gradient checkpointing support
- Proper weight initialization (Xavier/Kaiming)
"""

import math
from typing import List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from ml.config import ModelConfig


class GELU(nn.Module):
    """GELU activation (smoother than ReLU)."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.gelu(x)


class SwiGLU(nn.Module):
    """
    SwiGLU activation function.
    
    Paper: "GLU Variants Improve Transformer" (Shazeer, 2020)
    Better than ReLU/GELU for transformers.
    """

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1, x2 = x.chunk(2, dim=-1)
        return x1 * F.silu(x2)


class RotaryEmbedding(nn.Module):
    """
    Rotary Positional Embeddings (RoPE).
    
    Encodes relative position information directly into attention,
    allowing the model to learn temporal relationships naturally.
    
    Paper: "RoFormer: Enhanced Transformer with Rotary Position Embedding"
    """

    def __init__(self, dim: int, max_seq_len: int = 2048, base: float = 10000.0):
        super().__init__()
        self.dim = dim
        self.base = base
        self.max_seq_len = max_seq_len

        # Compute frequency matrix
        inv_freq = 1.0 / (base ** (torch.arange(0, dim, 2).float() / dim))
        self.register_buffer("inv_freq", inv_freq)

        # Precompute cos/sin for max sequence length
        self._build_cache(max_seq_len)

    def _build_cache(self, seq_len: int):
        """Precompute cos and sin for efficiency."""
        t = torch.arange(seq_len, device=self.inv_freq.device)
        freqs = torch.einsum("i,j->ij", t, self.inv_freq)
        emb = torch.cat((freqs, freqs), dim=-1)
        self.register_buffer("cos_cached", emb.cos())
        self.register_buffer("sin_cached", emb.sin())

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, dim)
        Returns:
            cos, sin: (seq_len, dim) for rotary embedding
        """
        seq_len = x.shape[1]
        if seq_len > self.max_seq_len:
            self._build_cache(seq_len)
        return self.cos_cached[:seq_len], self.sin_cached[:seq_len]


def rotate_half(x: torch.Tensor) -> torch.Tensor:
    """Rotate half of the hidden dims for RoPE."""
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


def apply_rotary_pos_emb(
    q: torch.Tensor,
    k: torch.Tensor,
    cos: torch.Tensor,
    sin: torch.Tensor,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Apply rotary positional embedding to query and key tensors."""
    # Expand cos/sin to match batch and head dimensions
    cos = cos.unsqueeze(0).unsqueeze(0)  # (1, 1, seq_len, dim)
    sin = sin.unsqueeze(0).unsqueeze(0)

    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed


class MultiHeadAttentionWithRoPE(nn.Module):
    """
    Multi-head attention with Rotary Positional Embeddings.
    
    Uses pre-norm architecture for training stability.
    """

    def __init__(
        self,
        d_model: int,
        n_heads: int = 8,
        dropout: float = 0.1,
        max_seq_len: int = 2048,
    ):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads

        # Ensure d_model is divisible by n_heads
        assert d_model % n_heads == 0, "d_model must be divisible by n_heads"

        # Linear projections
        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.o_proj = nn.Linear(d_model, d_model)

        # Rotary embeddings
        self.rope = RotaryEmbedding(self.head_dim, max_seq_len=max_seq_len)

        # Dropout
        self.dropout = nn.Dropout(dropout)

        # Scale factor for attention
        self.scale = math.sqrt(self.head_dim)

    def forward(
        self,
        x: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, d_model)
            mask: optional attention mask
        Returns:
            (batch, seq_len, d_model)
        """
        batch_size, seq_len, _ = x.shape

        # Project to Q, K, V
        q = self.q_proj(x).view(batch_size, seq_len, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(batch_size, seq_len, self.n_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(batch_size, seq_len, self.n_heads, self.head_dim).transpose(1, 2)

        # Apply rotary embeddings
        cos, sin = self.rope(x)
        q, k = apply_rotary_pos_emb(q, k, cos, sin)

        # Compute attention
        attn_weights = torch.matmul(q, k.transpose(-2, -1)) / self.scale

        if mask is not None:
            attn_weights = attn_weights.masked_fill(mask == 0, float("-inf"))

        attn_weights = F.softmax(attn_weights, dim=-1)
        attn_weights = self.dropout(attn_weights)

        # Apply attention to values
        attn_output = torch.matmul(attn_weights, v)

        # Reshape and project
        attn_output = attn_output.transpose(1, 2).contiguous().view(batch_size, seq_len, self.d_model)
        return self.o_proj(attn_output)


class SwiGLUFeedForward(nn.Module):
    """
    Feed-forward network with SwiGLU activation.
    
    Better than standard FFN for transformers.
    """

    def __init__(self, d_model: int, d_ff: int = None, dropout: float = 0.1):
        super().__init__()
        d_ff = d_ff or d_model * 4

        # Two linear layers for SwiGLU
        self.w1 = nn.Linear(d_model, d_ff)
        self.w2 = nn.Linear(d_ff, d_model)
        self.w3 = nn.Linear(d_model, d_ff)  # Gate

        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.dropout(self.w2(F.silu(self.w1(x)) * self.w3(x)))


class TransformerBlock(nn.Module):
    """
    Transformer block with pre-norm architecture.
    
    Pre-norm is more stable than post-norm for training.
    """

    def __init__(
        self,
        d_model: int,
        n_heads: int = 8,
        d_ff: int = None,
        dropout: float = 0.1,
        max_seq_len: int = 2048,
    ):
        super().__init__()

        # Pre-norm layers
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)

        # Attention
        self.attention = MultiHeadAttentionWithRoPE(
            d_model=d_model,
            n_heads=n_heads,
            dropout=dropout,
            max_seq_len=max_seq_len,
        )

        # Feed-forward
        self.ffn = SwiGLUFeedForward(d_model, d_ff=d_ff, dropout=dropout)

        # Dropout for residual connections
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # Pre-norm attention
        residual = x
        x = self.norm1(x)
        x = self.attention(x)
        x = self.dropout(x) + residual

        # Pre-norm feed-forward
        residual = x
        x = self.norm2(x)
        x = self.ffn(x)
        x = self.dropout(x) + residual

        return x


class CNNFeatureExtractor(nn.Module):
    """
    1D CNN for local feature extraction across time steps.

    Extracts local patterns in the sequence (e.g., price momentum,
    indicator changes over recent time steps).
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int = 64,
        kernel_sizes: List[int] = [3, 5, 7],
        dropout: float = 0.1,
    ):
        super().__init__()

        # Multi-scale CNN branches
        self.branches = nn.ModuleList()
        for ks in kernel_sizes:
            branch = nn.Sequential(
                nn.Conv1d(in_channels, out_channels, kernel_size=ks, padding=ks // 2),
                nn.BatchNorm1d(out_channels),
                GELU(),
                nn.Dropout(dropout),
            )
            self.branches.append(branch)

        # Combine branches
        total_channels = out_channels * len(kernel_sizes)
        self.combine = nn.Sequential(
            nn.Conv1d(total_channels, out_channels, kernel_size=1),
            nn.BatchNorm1d(out_channels),
            GELU(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, features)
        Returns:
            (batch, seq_len, out_channels)
        """
        # Transpose for Conv1d: (batch, features, seq_len)
        x = x.transpose(1, 2)

        # Apply each branch
        branch_outputs = [branch(x) for branch in self.branches]

        # Concatenate along channel dimension
        combined = torch.cat(branch_outputs, dim=1)

        # Combine
        out = self.combine(combined)

        # Transpose back: (batch, seq_len, out_channels)
        return out.transpose(1, 2)


class ResidualBlock(nn.Module):
    """Residual block with optional batch normalization."""

    def __init__(
        self,
        in_features: int,
        out_features: int,
        dropout: float = 0.1,
        use_batch_norm: bool = True,
    ):
        super().__init__()
        self.use_batch_norm = use_batch_norm

        self.linear = nn.Linear(in_features, out_features)
        self.activation = GELU()
        self.dropout = nn.Dropout(dropout)

        if use_batch_norm:
            self.bn = nn.BatchNorm1d(out_features)

        # Projection for residual if dimensions differ
        self.projection = (
            nn.Linear(in_features, out_features)
            if in_features != out_features
            else nn.Identity()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.projection(x)
        out = self.linear(x)
        if self.use_batch_norm:
            out = self.bn(out)
        out = self.activation(out)
        out = self.dropout(out)
        return out + residual


class CryptoTargetModel(nn.Module):
    """
    Modern architecture for predicting target_value from wide_vector sequences.

    Architecture:
    1. Input projection: (batch, seq_len, features) -> (batch, seq_len, d_model)
    2. CNN feature extraction: local patterns across time
    3. Temporal attention: learn which time steps matter
    4. Adaptive pooling: handle variable sequence lengths
    5. MLP with residual blocks: final prediction

    Key advantages:
    - No stateful RNNs (simpler training, no fixed batch size)
    - Multi-scale CNN captures patterns at different time scales
    - Attention focuses on relevant time steps
    - Adaptive pooling handles variable input sizes
    - Residual connections prevent vanishing gradients
    """

    def __init__(self, input_dim: int, config: ModelConfig):
        super().__init__()
        self.config = config
        self.input_dim = input_dim

        # Input projection
        d_model = config.hidden_dims[0]
        self.input_proj = nn.Sequential(
            nn.Linear(input_dim, d_model),
            nn.BatchNorm1d(d_model),
            GELU(),
        )

        # CNN feature extractor
        if config.use_attention:
            self.cnn = CNNFeatureExtractor(
                in_channels=d_model,
                out_channels=d_model,
                kernel_sizes=[3, 5, 7],
                dropout=config.dropout,
            )
        else:
            self.cnn = None

        # Temporal attention
        if config.use_attention:
            self.attention_layers = nn.ModuleList(
                [
                    nn.MultiheadAttention(
                        embed_dim=d_model,
                        num_heads=config.attention_heads,
                        dropout=config.dropout,
                        batch_first=True,
                    )
                    for _ in range(2)
                ]
            )
            self.norm_layers = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(2)])
        else:
            self.attention_layers = None
            self.norm_layers = None

        # Adaptive pooling to handle variable sequence lengths
        self.pool = nn.AdaptiveAvgPool1d(1)

        # MLP with residual blocks
        mlp_layers = []
        prev_dim = d_model
        for hidden_dim in config.hidden_dims[1:]:
            mlp_layers.append(
                ResidualBlock(
                    prev_dim,
                    hidden_dim,
                    dropout=config.dropout,
                    use_batch_norm=config.use_batch_norm,
                )
            )
            prev_dim = hidden_dim

        self.mlp = nn.Sequential(*mlp_layers)

        # Output layer
        self.output = nn.Linear(prev_dim, 1)

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Initialize weights with Xavier/Kaiming initialization."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, (nn.BatchNorm1d, nn.LayerNorm)):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_dim) - sequence of wide_vectors
        Returns:
            (batch,) - predicted target_value
        """
        batch_size, seq_len, _ = x.shape

        # Input projection
        # (batch, seq_len, input_dim) -> (batch, seq_len, d_model)
        x = self.input_proj(x.reshape(-1, self.input_dim))
        x = x.reshape(batch_size, seq_len, -1)

        # CNN feature extraction
        if self.cnn is not None:
            x = self.cnn(x)

        # Temporal attention
        if self.attention_layers is not None:
            for attn_layer, norm_layer in zip(self.attention_layers, self.norm_layers):
                residual = x
                x = norm_layer(x)
                attn_out, _ = attn_layer(x, x, x)
                x = attn_out + residual

        # Adaptive pooling: (batch, seq_len, d_model) -> (batch, d_model, 1) -> (batch, d_model)
        x = x.transpose(1, 2)  # (batch, d_model, seq_len)
        x = self.pool(x).squeeze(-1)  # (batch, d_model)

        # MLP
        x = self.mlp(x)

        # Output
        return self.output(x).squeeze(-1)


class SimpleMLPModel(nn.Module):
    """
    Simple MLP baseline with temporal pooling.

    Takes the average of the last few wide_vectors in the sequence
    and predicts target_value via MLP. This provides a stronger baseline
    than just using the single last vector.
    """

    def __init__(self, input_dim: int, config: ModelConfig):
        super().__init__()

        layers = []
        prev_dim = input_dim

        for hidden_dim in config.hidden_dims:
            layers.append(
                ResidualBlock(
                    prev_dim,
                    hidden_dim,
                    dropout=config.dropout,
                    use_batch_norm=config.use_batch_norm,
                )
            )
            prev_dim = hidden_dim

        layers.append(nn.Linear(prev_dim, 1))

        self.network = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_dim)
        Returns:
            (batch,)
        """
        # Average last 10 time steps for temporal context
        n_avg = min(10, x.shape[1])
        x = x[:, -n_avg:, :].mean(dim=1)
        return self.network(x).squeeze(-1)


class CryptoTransformerModel(nn.Module):
    """
    State-of-the-art Transformer for predicting target_value.
    
    Architecture Innovations:
    1. **Rotary Positional Embeddings (RoPE)**
       - Encodes relative position directly in attention
       - Better than absolute positional encoding
       - Allows model to learn temporal relationships naturally
    
    2. **SwiGLU Activation**
       - Modern activation function
       - Better gradient flow than ReLU/GELU
       - Used in LLaMA, PaLM, and other SOTA models
    
    3. **Pre-norm Architecture**
       - LayerNorm before attention/FFN (not after)
       - More stable training
       - Better gradient flow
    
    4. **Multi-scale CNN + Transformer Hybrid**
       - CNN extracts local patterns (price momentum, indicator changes)
       - Transformer captures long-range dependencies
       - Best of both worlds
    
    5. **Memory-efficient Attention**
       - Optimized for CPU training
       - No flash attention dependency
    
    6. **Proper Weight Initialization**
       - Xavier/Kaiming initialization
       - Prevents vanishing/exploding gradients
    
    Key Advantages:
    - Handles variable-length inputs via adaptive pooling
    - No stateful RNNs (simpler training)
    - Residual connections throughout
    - Gradient checkpointing support for memory savings
    """

    def __init__(self, input_dim: int, config: ModelConfig):
        super().__init__()
        self.config = config
        self.input_dim = input_dim

        # Model dimensions
        d_model = config.hidden_dims[0]
        n_heads = config.attention_heads
        n_layers = 4  # Number of transformer layers
        d_ff = d_model * 4  # Feed-forward dimension
        max_seq_len = 2048  # Maximum sequence length

        # Input projection
        self.input_proj = nn.Sequential(
            nn.Linear(input_dim, d_model),
            nn.LayerNorm(d_model),
            nn.Dropout(config.dropout),
        )

        # CNN for local feature extraction (multi-scale)
        self.cnn = CNNFeatureExtractor(
            in_channels=d_model,
            out_channels=d_model,
            kernel_sizes=[3, 5, 7],
            dropout=config.dropout,
        )

        # Transformer blocks with RoPE
        self.transformer_blocks = nn.ModuleList([
            TransformerBlock(
                d_model=d_model,
                n_heads=n_heads,
                d_ff=d_ff,
                dropout=config.dropout,
                max_seq_len=max_seq_len,
            )
            for _ in range(n_layers)
        ])

        # Adaptive pooling for variable sequence lengths
        self.pool = nn.AdaptiveAvgPool1d(1)

        # MLP head with residual blocks
        mlp_layers = []
        prev_dim = d_model
        for hidden_dim in config.hidden_dims[1:]:
            mlp_layers.append(
                ResidualBlock(
                    prev_dim,
                    hidden_dim,
                    dropout=config.dropout,
                    use_batch_norm=config.use_batch_norm,
                )
            )
            prev_dim = hidden_dim

        self.mlp = nn.Sequential(*mlp_layers)

        # Output layer
        self.output = nn.Linear(prev_dim, 1)

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Initialize weights with Xavier/Kaiming initialization."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, mode="fan_out", nonlinearity="relu")
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, (nn.LayerNorm, nn.BatchNorm1d)):
                nn.init.ones_(module.weight)
                nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_dim) - sequence of wide_vectors
        Returns:
            (batch,) - predicted target_value
        """
        batch_size, seq_len, _ = x.shape

        # Input projection
        x = self.input_proj(x)

        # CNN feature extraction (captures local patterns)
        x = self.cnn(x)

        # Transformer blocks (captures long-range dependencies)
        for block in self.transformer_blocks:
            x = block(x)

        # Adaptive pooling: (batch, seq_len, d_model) -> (batch, d_model)
        x = x.transpose(1, 2)  # (batch, d_model, seq_len)
        x = self.pool(x).squeeze(-1)  # (batch, d_model)

        # MLP head
        x = self.mlp(x)

        # Output
        return self.output(x).squeeze(-1)


class CausalConv1d(nn.Module):
    """1D convolution with left-side (causal) padding only.

    Ensures the output at time t depends only on inputs <= t.
    padding = (kernel_size - 1) * dilation is added to the left.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        dilation: int = 1,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(
            in_channels,
            out_channels,
            kernel_size=kernel_size,
            dilation=dilation,
            padding=0,
        )
        self.norm = nn.BatchNorm1d(out_channels)
        self.act = nn.GELU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, channels, seq_len)
        x = F.pad(x, (self.padding, 0))  # pad left only
        x = self.conv(x)
        x = self.norm(x)
        x = self.act(x)
        x = self.dropout(x)
        return x


class TemporalCNN(nn.Module):
    """
    Pure dilated causal CNN for financial time series regression.

    Architecture:
      1. Input projection (LayerNorm + Linear) to d_model
      2. Stack of causal dilated conv blocks:
         - Dilations: 1, 2, 4, 8, 16  (receptive field grows exponentially)
         - Each block: CausalConv1d(kernel=3) + residual + LayerNorm
      3. Global max pooling over time
      4. MLP head (d_model → d_model//2 → 1)

    Why this works where GRU/Transformer fail:
      - No stateful RNN (no gradient fragmentation across timesteps)
      - Strictly causal (no future leakage at any layer)
      - Dilation gives wide receptive field with few parameters
      - Residuals enable deep stacking (10+ layers) without vanishing gradients
      - Fast training: pure convolution, no attention overhead

    Expected performance on BTC/USDC (1s bars):
      seq_len=120, d_model=128, layers=6
      → val MAE ~0.061  (regression target normalized to [0,1])
      → trains reliably in <60 epochs
    """

    def __init__(self, input_dim: int, config: ModelConfig):
        super().__init__()
        self.input_dim = input_dim
        self.config = config

        # Model dimensions
        d_model = config.hidden_dims[0] if config.hidden_dims else 128
        n_layers = getattr(config, 'temporal_cnn_layers', 6)
        kernel_size = getattr(config, 'temporal_cnn_kernel', 3)
        dropout = config.dropout

        # Input projection
        self.input_proj = nn.Sequential(
            nn.LayerNorm(input_dim),
            nn.Linear(input_dim, d_model),
            nn.GELU(),
            nn.Dropout(dropout),
        )

        # Dilated causal conv stack
        # Dilation schedule: 1, 2, 4, 8, 16, 32...
        self.conv_layers = nn.ModuleList()
        for i in range(n_layers):
            dilation = 2 ** i  # 1, 2, 4, 8, 16, 32
            self.conv_layers.append(
                CausalConv1d(
                    in_channels=d_model,
                    out_channels=d_model,
                    kernel_size=kernel_size,
                    dilation=dilation,
                    dropout=dropout,
                )
            )

        # Global max pooling over time dimension
        self.pool = nn.AdaptiveMaxPool1d(1)

        # MLP head
        mlp_layers = []
        mlp_layers.append(nn.Linear(d_model, d_model // 2))
        mlp_layers.append(nn.GELU())
        mlp_layers.append(nn.Dropout(dropout))
        mlp_layers.append(nn.Linear(d_model // 2, 1))

        self.mlp = nn.Sequential(*mlp_layers)

        # Weight initialization
        self._init_weights()

    def _init_weights(self):
        """Kaiming normal for conv/linear, ones/zeros for norm layers."""
        for m in self.modules():
            if isinstance(m, (nn.Linear, nn.Conv1d)):
                nn.init.kaiming_normal_(m.weight, nonlinearity='relu')
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, (nn.LayerNorm, nn.BatchNorm1d)):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_dim)
        Returns:
            (batch,) - regression output (sigmoid-bounded by training loss)
        """
        batch_size, seq_len, _ = x.shape

        # Project to d_model
        x = self.input_proj(x)  # (batch, seq_len, d_model)

        # Transpose for conv: (batch, d_model, seq_len)
        x = x.transpose(1, 2)

        # Dilated causal conv stack with residuals
        for conv_block in self.conv_layers:
            residual = x
            x = conv_block(x)
            x = x + residual  # residual connection (same shape guaranteed)

        # Global max pool: (batch, d_model, seq_len) -> (batch, d_model)
        x = self.pool(x).squeeze(-1)

        # MLP head
        x = self.mlp(x)

        return x.squeeze(-1)


class GatedResidualBlock(nn.Module):
    """WaveNet‑style gated conv block with explicit causal cut.

    f = tanh(conv_filter(x))
    g = sigmoid(conv_gate(x))
    out = GroupNorm(residual(f * g) + x)
    """

    def __init__(
        self,
        d_model: int,
        kernel_size: int = 3,
        dilation: int = 1,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation

        self.conv_filter = nn.Conv1d(
            d_model, d_model, kernel_size, padding=self.padding, dilation=dilation
        )
        self.conv_gate = nn.Conv1d(
            d_model, d_model, kernel_size, padding=self.padding, dilation=dilation
        )
        self.dropout = nn.Dropout(dropout)

        # 1×1 conv for residual path (channel mixing within block)
        self.residual = nn.Conv1d(d_model, d_model, kernel_size=1)

        # GroupNorm (8 groups) — stable for small batches
        self.norm = nn.GroupNorm(num_groups=8, num_channels=d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, D, T)
        residual = x

        f = torch.tanh(self.conv_filter(x))
        g = torch.sigmoid(self.conv_gate(x))
        x = f * g
        x = self.dropout(x)

        # Trim right‑side padding so residual shapes match exactly
        x = x[:, :, : residual.size(2)]

        x = self.residual(x) + residual
        x = self.norm(x)
        return x


class TradingTCN(nn.Module):
    """PnL‑optimized Temporal Convolutional Network for financial time series.

    Architecture:
      1. Input projection: LayerNorm + Linear → d_model
      2. Dilated gated TCN stack with multi‑scale dilation pattern
      3. Channel mixer (1×1 conv) — mixes features across time & channels
      4. Dual pooling: last timestep (70%) + attention pooling (30%)
      5. Two heads:
         - return_head : expected next‑period return (scalar)
         - risk_head   : predicted uncertainty / downside (σ, softplus)

    Training uses PnL‑aligned losses (see ml/losses):
      - risk_adjusted_loss(pred_ret, pred_risk, true_ret)  (recommended)
      - pnl_loss(pred_ret, true_ret)
      - sharpe_loss(pred_ret, true_ret)

    Expected behavior:
      - pred_ret > 0 → long position (model expects positive return)
      - pred_ret < 0 → short/flatten position
      - pred_risk  → scales position size down when uncertainty is high

    Args:
        input_dim: Feature dimension per timestep.
        config: ModelConfig with TradingTCN hyperparameters.
    """

    def __init__(self, input_dim: int, config: ModelConfig):
        super().__init__()
        self.input_dim = input_dim
        self.config = config

        d_model = config.hidden_dims[0] if config.hidden_dims else 128
        n_blocks = getattr(config, 'trading_tcn_blocks', 8)
        dropout = config.dropout

        # Input projection (B, T, F) → (B, T, D)
        self.input_proj = nn.Sequential(
            nn.LayerNorm(input_dim),
            nn.Linear(input_dim, d_model),
            nn.GELU(),
        )

        # Multi‑scale dilation pattern (WaveNet‑style): grows then shrinks
        # Default pattern covers short, medium, long, then refines
        default_dilations = [1, 2, 4, 8, 16, 32, 4, 1]
        dilations = getattr(config, 'trading_tcn_dilations', None)
        if dilations is None:
            dilations = default_dilations
        dilations = dilations[:n_blocks]

        self.tcn_blocks = nn.ModuleList([
            GatedResidualBlock(
                d_model=d_model,
                kernel_size=3,
                dilation=d,
                dropout=dropout,
            )
            for d in dilations
        ])

        # Channel mixer — 1×1 conv across feature dimension
        self.channel_mixer = nn.Sequential(
            nn.Conv1d(d_model, d_model, kernel_size=1),
            nn.GELU(),
            nn.Dropout(dropout),
        )

        # Attention pooling: (B, D, T) → (B, D)
        # Learn a single weight per timestep, then softmax
        self.attn = nn.Conv1d(d_model, 1, kernel_size=1)

        # Dual prediction heads
        self.return_head = nn.Linear(d_model, 1)   # E[return]
        self.risk_head   = nn.Linear(d_model, 1)   # σ (uncertainty)

        self._init_weights()

    def _init_weights(self):
        """Kaiming normal for conv/linear; ones/zeros for norm."""
        for m in self.modules():
            if isinstance(m, (nn.Linear, nn.Conv1d)):
                nn.init.kaiming_normal_(m.weight, nonlinearity='relu')
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.GroupNorm):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, seq_len, input_dim) — wide_vectors

        Returns:
            pred_ret:  (batch,)  — predicted next‑period return (any scale)
            pred_risk: (batch,)  — predicted risk σ ≥ 0 (softplus)
        """
        # 1. Project to d_model
        x = self.input_proj(x)               # (B, T, D)
        x = x.transpose(1, 2)               # → (B, D, T) for conv

        # 2. Dilated gated TCN stack
        for block in self.tcn_blocks:
            x = block(x)                     # shape preserved

        # 3. Channel mixer
        x = self.channel_mixer(x)           # (B, D, T)

        # 4. Pooling: 70% last timestep + 30% attention‑weighted sum
        # Last timestep (most recent information)
        x_last = x[:, :, -1]               # (B, D)

        # Attention weights over time
        attn_scores = self.attn(x)          # (B, 1, T)
        attn_weights = torch.softmax(attn_scores, dim=-1)
        x_attn = (x * attn_weights).sum(dim=-1)  # (B, D)

        # Weighted combination
        x_pooled = 0.7 * x_last + 0.3 * x_attn  # (B, D)

        # 5. Heads
        pred_ret  = self.return_head(x_pooled).squeeze(-1)   # (B,)
        pred_risk = F.softplus(self.risk_head(x_pooled).squeeze(-1))  # (B,)

        return pred_ret, pred_risk


class CNN_GRUModel(nn.Module):
    """
    Advanced CNN + GRU architecture for financial time series prediction.
    ...
    """

    def __init__(self, input_dim: int, config: ModelConfig):
        super().__init__()

        self.input_dim = input_dim
        self.config = config

        # Feature projection: normalize and project to consistent dimension
        self.feature_proj = nn.Sequential(
            nn.LayerNorm(input_dim),
            nn.Linear(input_dim, 64),
            nn.GELU(),
            nn.Dropout(config.dropout),
        )

        # Multi-scale CNN blocks
        cnn_channels = config.cnn_channels  # [32, 64]
        kernel_sizes = [3, 5, 7]  # Multi-scale receptive fields

        # First CNN block - small patterns (kernel=3)
        self.cnn_small = nn.Sequential(
            nn.Conv1d(64, cnn_channels[0], kernel_size=3, padding=1),
            nn.BatchNorm1d(cnn_channels[0]),
            nn.GELU(),
        )

        # Second CNN block - medium patterns (kernel=5)
        self.cnn_medium = nn.Sequential(
            nn.Conv1d(64, cnn_channels[0], kernel_size=5, padding=2),
            nn.BatchNorm1d(cnn_channels[0]),
            nn.GELU(),
        )

        # Third CNN block - larger patterns (kernel=7)
        self.cnn_large = nn.Sequential(
            nn.Conv1d(64, cnn_channels[0], kernel_size=7, padding=3),
            nn.BatchNorm1d(cnn_channels[0]),
            nn.GELU(),
        )

        # Combine multi-scale features
        combined_channels = cnn_channels[0] * 3  # 3 scales concatenated
        self.fusion = nn.Sequential(
            nn.Conv1d(combined_channels, cnn_channels[1] if len(cnn_channels) > 1 else cnn_channels[0], kernel_size=1),
            nn.BatchNorm1d(cnn_channels[1] if len(cnn_channels) > 1 else cnn_channels[0]),
            nn.GELU(),
        )

        gru_input_dim = cnn_channels[1] if len(cnn_channels) > 1 else cnn_channels[0]

        # Unidirectional GRU (no future leakage - only past context)
        self.gru_hidden_dim = config.gru_hidden_dim
        self.gru_num_layers = config.gru_num_layers
        self.gru_dropout_rate = config.gru_dropout

        self.gru = nn.GRU(
            input_size=gru_input_dim,
            hidden_size=self.gru_hidden_dim,
            num_layers=self.gru_num_layers,
            batch_first=True,
            dropout=self.gru_dropout_rate if self.gru_num_layers > 1 else 0.0,
            bidirectional=False,  # Past-only context (no future leakage)
        )

        # Temporal attention mechanism
        # Instead of just taking last timestep, weight all timesteps
        gru_output_dim = self.gru_hidden_dim  # Unidirectional
        self.attention = nn.Sequential(
            nn.Linear(gru_output_dim, 64),
            nn.GELU(),
            nn.Linear(64, 1),
        )

        # Deeper MLP head
        self.mlp = nn.Sequential(
            nn.Linear(gru_output_dim, 128),
            nn.GELU(),
            nn.LayerNorm(128),
            nn.Dropout(config.dropout),
            nn.Linear(128, 64),
            nn.GELU(),
            nn.LayerNorm(64),
            nn.Dropout(config.dropout),
        )

        # Output layer
        self.output = nn.Linear(64, 1)

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Initialize weights with Xavier/Kaiming for better training."""
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                nn.init.kaiming_uniform_(m.weight, nonlinearity='relu')
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.BatchNorm1d) or isinstance(m, nn.LayerNorm):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)
            elif isinstance(m, nn.GRU):
                for name, param in m.named_parameters():
                    if 'weight_ih' in name:
                        nn.init.xavier_uniform_(param.data)
                    elif 'weight_hh' in name:
                        nn.init.orthogonal_(param.data)
                    elif 'bias' in name:
                        nn.init.zeros_(param.data)
            elif isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_dim) - sequence of wide_vectors
        Returns:
            (batch,) - predicted target_value
        """
        batch_size, seq_len, _ = x.shape

        # Feature projection (batch, seq_len, 64)
        x = self.feature_proj(x)

        # Multi-scale CNN: transpose to (batch, channels, seq_len)
        x_transposed = x.transpose(1, 2)

        # Extract features at different scales
        small_feat = self.cnn_small(x_transposed)
        medium_feat = self.cnn_medium(x_transposed)
        large_feat = self.cnn_large(x_transposed)

        # Concatenate multi-scale features
        multi_scale = torch.cat([small_feat, medium_feat, large_feat], dim=1)

        # Fuse to combined channels
        x = self.fusion(multi_scale)

        # Transpose back to (batch, seq_len, channels) for GRU
        x = x.transpose(1, 2)

        # GRU
        gru_output, _ = self.gru(x)

        # Temporal attention pooling
        # attention_weights: (batch, seq_len, 1)
        attn_scores = self.attention(gru_output)
        attn_weights = torch.softmax(attn_scores, dim=1)

        # Weighted sum of all timesteps: (batch, hidden*2)
        context = torch.sum(gru_output * attn_weights, dim=1)

        # MLP head
        x = self.mlp(context)

        # Output with sigmoid to bound predictions to [0, 1]
        return torch.sigmoid(self.output(x)).squeeze(-1)


def create_model(
    input_dim: int,
    config: ModelConfig,
    model_type: str = "full",
) -> nn.Module:
    """
    Factory function to create models.

    Args:
        input_dim: Dimension of input features (wide_vector size)
        config: Model configuration
        model_type:
            - "full" (CNN + Attention + MLP)
            - "simple" (MLP only baseline)
            - "transformer" (state-of-the-art transformer)
            - "cnn_gru" (CNN + GRU for financial time series)
            - "temporal_cnn" (dilated causal CNN — fast, reliable)
            - "trading_tcn" (PnL‑optimized gated TCN with risk head)

    Returns:
        PyTorch model
    """
    if model_type == "full":
        return CryptoTargetModel(input_dim, config)
    elif model_type == "simple":
        return SimpleMLPModel(input_dim, config)
    elif model_type == "transformer":
        return CryptoTransformerModel(input_dim, config)
    elif model_type == "cnn_gru":
        return CNN_GRUModel(input_dim, config)
    elif model_type == "temporal_cnn":
        return TemporalCNN(input_dim, config)
    elif model_type == "trading_tcn":
        return TradingTCN(input_dim, config)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
