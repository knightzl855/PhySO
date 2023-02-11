import torch
import numpy as np


def safe_cross_entropy(p, logq, dim=-1):
    safe_logq = torch.where(p == 0, torch.ones_like(logq), logq)
    return -torch.sum(p * safe_logq, dim=dim)


def loss_func(logits_train, ideal_probs_train, R_train, baseline, lengths, gamma_decay, entropy_weight, ):
    """
    Loss function for reinforcing symbolic programs.
    Parameters
    ----------
    logits_train       : torch.tensor of shape (max_time_step, n_train, n_choices,)
        Probabilities generated by the rnn (for each step along program length, for each program in training sub-batch,
        for each choosable token).
    ideal_probs_train  : torch.tensor of shape (max_time_step, n_train, n_choices,)
        One-hot ideal probabilities to reinforce (for each step along program length, for each program in training
        sub-batch, for each choosable token).
    R_train            : torch.tensor of shape (n_train,)
        Rewards of programs (for each program in training sub-batch).
    baseline           : float
        Baseline to subtract to rewards.
    lengths            : torch.tensor of shape (n_train,)
        Effective length of programs not counting placeholders fillers (for each program in training sub-batch).
    gamma_decay        : float
        Weight of power law to use along program length: gamma_decay**t where t is the step in the sequence.
        (gamma_decay < 1 gives more important to first tokens and gamma_decay > 1 gives more weight to last tokens).
    entropy_weight     : float
        Weight to give to entropy part of the loss.
    Returns
    -------
    loss : float
        Loss value.
    """

    # Getting shape
    (max_time_step, n_train, n_choices,) = ideal_probs_train.shape

    # ----- Length mask -----
    # Lengths mask (avoids learning out of range of symbolic functions)

    mask_length_np = np.tile(np.arange(0, max_time_step), (n_train, 1)  # (n_train, max_time_step,)
                             ).astype(int) < np.tile(lengths, (max_time_step, 1)).transpose()
    mask_length_np = mask_length_np.transpose().astype(float)  # (max_time_step, n_train,)
    mask_length = torch.tensor(mask_length_np, requires_grad=False)  # (max_time_step, n_train,)

    # ----- Entropy mask -----
    # Entropy mask (weighting differently along sequence dim)

    entropy_gamma_decay = np.array([gamma_decay ** t for t in range(max_time_step)])  # (max_time_step,)
    entropy_decay_mask_np = np.tile(entropy_gamma_decay,
                                    (n_train, 1)).transpose() * mask_length_np  # (max_time_step, n_train,)
    entropy_decay_mask = torch.tensor(entropy_decay_mask_np, requires_grad=False)  # (max_time_step, n_train,)

    # ----- Loss : Gradient Policy -----

    # Normalizing over action dim probs and logprobs
    probs = torch.nn.functional.softmax(logits_train, dim=2)  # (max_time_step, n_train, n_choices,)
    logprobs = torch.nn.functional.log_softmax(logits_train, dim=2)  # (max_time_step, n_train, n_choices,)

    # Sum over action dim
    neglogp_per_step = safe_cross_entropy(ideal_probs_train, logprobs, dim=2)  # (max_time_step, n_train,)
    # Sum over sequence dim
    neglogp = torch.sum(neglogp_per_step * mask_length, dim=0)  # (n_train,)

    # Mean over training samples of batch
    loss_gp = torch.mean((R_train - baseline) * neglogp)

    # ----- Loss : Entropy -----

    # Sum over action dim
    entropy_per_step = safe_cross_entropy(probs, logprobs, dim=2)  # (max_time_step, n_train,)
    # Sum over sequence dim
    entropy = torch.sum(entropy_per_step * entropy_decay_mask, dim=0)  # (n_train,)

    loss_entropy = -entropy_weight * torch.mean(entropy)

    # ----- Loss -----
    loss = loss_gp + loss_entropy

    return loss


