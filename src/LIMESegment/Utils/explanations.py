
from scipy import signal
import numpy as np
import stumpy
from sklearn.linear_model import Ridge
from sklearn.utils import check_random_state
from fastdtw import fastdtw
import random

def NNSegment(t, window_size, change_points):
    
    n_timesteps, n_features = t.shape
    
    # Use matrix profile for multivariate time series
    mp = stumpy.mstump(t, m=window_size)
    
    # Here, we consider the first dimension for the nearest neighbor change detection
    proposed_cp = [i for i in range(0, mp.shape[0]-1) if mp[i+1, 0, 1] != mp[i, 0, 1] + 1]
    
    tolerance = int(window_size/2)
    variances = []

    for idx in proposed_cp:
        mean_change = np.abs(np.mean(t[idx-tolerance:idx, :], axis=0) - np.mean(t[idx:idx+tolerance, :], axis=0))
        std_change = np.abs(np.std(t[idx-tolerance:idx, :], axis=0) - np.std(t[idx:idx+tolerance, :], axis=0))
        
        # We aggregate the mean and std changes across features using their L2 norm (Euclidean distance)
        mean_change_norm = np.linalg.norm(mean_change)
        std_change_norm = np.linalg.norm(std_change)
        
        std_mean = np.mean([np.linalg.norm(np.std(t[idx-tolerance:idx, :], axis=0)), np.linalg.norm(np.std(t[idx:idx+tolerance, :], axis=0))])
        
        variances.append(mean_change_norm * std_change_norm / std_mean)
    
    sorted_idx = np.flip(np.array(variances).argsort())
    sorted_cp = [proposed_cp[idx] for idx in sorted_idx]
    
    selected_cp = []
    covered = list(np.arange(0, tolerance))
    ic, i = 0, 0
    while ic < change_points:
        if i == len(sorted_cp):
            break
        if sorted_cp[i] not in covered:
            ic += 1
            selected_cp.append(sorted_cp[i])
            covered = covered + list(np.arange(sorted_cp[i], sorted_cp[i]+tolerance))
            covered = covered + list(np.arange(sorted_cp[i]-tolerance, sorted_cp[i]))
        i += 1
    selected_cp = np.sort(np.asarray(selected_cp))
    
    return list(selected_cp)



def backgroundIdentification(original_signal, f=40):
    """
    Adjusted for multivariate time series.
    """

    n_timesteps, n_features = original_signal.shape
    xrec_all_features = []

    for feature_idx in range(n_features):
        feature_signal = original_signal[:, feature_idx]

        # Calculating the Short-Time Fourier Transform (STFT) for the current feature
        f, t, Zxx = signal.stft(feature_signal, 1, nperseg=f)
        frequency_composition_abs = np.abs(Zxx)
        measures = []

        for freq, freq_composition in zip(f, frequency_composition_abs):
            measures.append(np.mean(freq_composition) / np.std(freq_composition))

        max_value = max(measures)
        selected_frequency = measures.index(max_value)
        weights = 1 - (measures / sum(measures))
        dummymatrix = np.zeros((len(f), len(t)))
        dummymatrix[selected_frequency, :] = 1

        background_frequency = Zxx * dummymatrix

        # Using the Inverse Short-Time Fourier Transform (ISTFT) to reconstruct the background signal
        _, xrec = signal.istft(background_frequency, 1)
        xrec = xrec[:n_timesteps]

        xrec_all_features.append(xrec)

    xrec_all_features = np.stack(xrec_all_features, axis=-1)
    return xrec_all_features

def RBP(generated_samples_interpretable, original_signal, segment_indexes, f):
    """
    Adjusted for multivariate time series.
    """

    n_timesteps, n_features = original_signal.shape
    generated_samples_raw = []

    # Assuming each feature of the original signal has its own distinct background
    # Thus, extracting background for each feature separately
    xrec = np.stack([backgroundIdentification(original_signal[:, feature_idx]) for feature_idx in range(n_features)], axis=-1)

    for sample_interpretable in generated_samples_interpretable:
        raw_signal = original_signal.copy()

        for index in range(len(sample_interpretable) - 1):
            if sample_interpretable[index] == 0:
                index0 = segment_indexes[index]
                index1 = segment_indexes[index+1]
                raw_signal[index0:index1, :] = xrec[index0:index1, :]
        
        generated_samples_raw.append(np.asarray(raw_signal))

    return np.asarray(generated_samples_raw)
    
def LIMESegment(example, model, model_type='class', distance='dtw', n=100, window_size=None, cp=None, f=None, random_state=None):
    random_state = check_random_state(random_state)
    n_timesteps, n_features = example.shape

    if window_size is None:
        window_size = int(n_timesteps/5)
    if cp is None:
        cp = 3
    if f is None: 
        f = int(n_timesteps/10)
    
    # Adjusting to keep the multivariate structure
    cp_indexes = NNSegment(example, window_size, cp, n_features) 
    segment_indexes = [0] + cp_indexes + [-1]
    
    # Adjusting random samples generation for multivariate series
    generated_samples_interpretable = [random_state.binomial(1, 0.5, len(cp_indexes) + 1) for _ in range(0, n)]
    generated_samples_raw = RBP(generated_samples_interpretable, example, segment_indexes, f, n_features) 
    
    sample_predictions = model.predict(generated_samples_raw)
    
    if model_type == 'proba':
        y_labels = np.argmax(sample_predictions, axis=1)
    elif isinstance(model_type, int):
        y_labels = sample_predictions[:, model_type]
    else:
        y_labels = sample_predictions
    
    if distance == 'dtw':
        distances = np.asarray([fastdtw(example, sample)[0] for sample in generated_samples_raw])
        weights = np.exp(-(np.abs((distances - np.mean(distances))/np.std(distances)).reshape(n,)))
    elif distance == 'euclidean':
        distances = np.asarray([np.linalg.norm(np.ones((len(cp_indexes) + 1, n_features)) - x, axis=1) for x in generated_samples_interpretable])
        weights = np.exp(-(np.abs(distances**2/0.75*(len(segment_indexes)**2)).reshape(n,)))
        
    clf = Ridge(random_state=random_state)
    clf.fit(generated_samples_interpretable, y_labels, weights)
    
    return clf.coef_, segment_indexes





def background_perturb(original_signal, index0, index1, X_background):
    perturbed_signal = original_signal.copy()
    selected_background_ts = X_background[random.randint(0, 20)]
    perturbed_signal[index0:index1] = selected_background_ts.reshape(perturbed_signal.shape)[index0:index1]   
    return np.asarray(perturbed_signal)

def mean_perturb(original_signal, index0, index1, mean_value, ws):
    perturbed_signal = original_signal.copy()
    mean_signal = np.ones(original_signal.shape)*mean_value
    perturbed_signal[index0:index1] = mean_signal[index0:index1]
    return perturbed_signal

def calculate_mean(cp_indexes, X_background, ws):
    sample_averages = []
    for ts in X_background: 
        window_averages = np.mean([np.mean(ts[i:i+ws]) for i in cp_indexes])
        sample_averages.append(window_averages)
    return np.mean(sample_averages)


def LEFTIST(example, model,  X_background, model_type="class", n=100):
    ts_length = example.shape[0]
    cp_indexes = [i for i in range(0,example.shape[0],int(example.shape[0]/10))]
    example_interpretable = np.ones(len(cp_indexes))
    generated_samples_interpretable = [ np.random.binomial(1, 0.5, len(cp_indexes)) for _ in range(0,n)]
    generated_samples_original = []
    segment_indexes = cp_indexes + [-1]
    for sample_interpretable in generated_samples_interpretable:
        raw_sample = example.copy()
        for index in range(0,len(sample_interpretable)):
            if sample_interpretable[index] == 0:
                index0 = segment_indexes[index]
                index1 = segment_indexes[index+1]
                raw_sample = background_perturb(raw_sample,index0,index1,X_background)
        generated_samples_original.append((raw_sample))
    
    sample_predictions = model.predict(np.asarray(generated_samples_original))
    if model_type == 'proba':
        y_labels = np.argmax(sample_predictions, axis=1)
    else:
        y_labels = sample_predictions

    distances = np.asarray([np.linalg.norm(np.ones(len(cp_indexes))-x) for x in generated_samples_interpretable])
    weights = np.exp(-(np.abs(distances**2/(len(segment_indexes)**2))))
    clf = Ridge()
    clf.fit(generated_samples_interpretable,y_labels,weights)
    return clf.coef_, cp_indexes

    distances = np.asarray([np.linalg.norm(np.ones(len(cp_indexes))-x) for x in generated_samples_interpretable])
    weights = np.exp(-(np.abs(distances**2/(len(segment_indexes)**2))))
    clf = Ridge()
    clf.fit(generated_samples_interpretable,y_labels,weights)
    return clf.coef_, cp_indexes

def NEVES(example, model, X_background, model_type="class", n=100):
    ts_length = example.shape[0]
    cp_indexes = [i for i in range(0,example.shape[0],int(example.shape[0]/10))]
    example_interpretable = np.ones(len(cp_indexes))
    generated_samples_interpretable = [ np.random.binomial(1, 0.5, len(cp_indexes)) for _ in range(0,n)]
    generated_samples_original = []
    mean_perturb_value = calculate_mean(cp_indexes, X_background, int(cp_indexes[1]-cp_indexes[0]))
    segment_indexes = cp_indexes + [ts_length]
    for sample_interpretable in generated_samples_interpretable:
        raw_sample = example.copy()
        for index in range(0,len(sample_interpretable)):
            if sample_interpretable[index] == 0:
                index0 = segment_indexes[index]
                index1 = segment_indexes[index+1]
                raw_sample = mean_perturb(raw_sample,index0,index1,mean_perturb_value,int(cp_indexes[1]-cp_indexes[0]))
        generated_samples_original.append(raw_sample)

    sample_predictions = model.predict(np.asarray(generated_samples_original))
    if model_type == 'proba':
        y_labels = np.argmax(sample_predictions, axis=1)
    else:
        y_labels = sample_predictions

    distances = np.asarray([np.linalg.norm(np.ones(len(cp_indexes))-x) for x in generated_samples_interpretable])
    weights = np.exp(-(np.abs(distances**2/(len(segment_indexes)**2))).reshape(n,))
    clf = Ridge()
    clf.fit(generated_samples_interpretable,y_labels,weights)
    return clf.coef_, cp_indexes


