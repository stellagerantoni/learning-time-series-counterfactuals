
from scipy import signal
import numpy as np
import stumpy
from sklearn.linear_model import Ridge
from sklearn.utils import check_random_state
from fastdtw import fastdtw
import random


def NNSegment(t, window_size, change_points):
    """Return the change points of given time series
    Input: 
        t - numpy array of size T
        window_size - int where window_size < T 
        change_points - user specified number of change points
    Output: 
        np.array of change point indexes 
    """
    """Return the change points of given time series
    Input: 
        t - numpy array of size T
        window_size - int where window_size < T 
        change_points - user specified number of change points
    Output: 
        np.array of change point indexes 
    """
    #mp is a 2-d (t - m + 1,4)array with 4 columns 
    # c1: uclidean distance of the subsequence to the closesed neighbor
    #c2: the index of the colsesed neigthboor
    #c3: the index of the left clossesed neighboor
    #c4: the index of the right neirest neighboor
    mp = stumpy.stump(t, m=window_size)
    #proposed_cp is propose changes if the distance of the row i+1 is diffrent than the row i plus 1  then it is proposed as a sinificant change in the destance matrix.
    proposed_cp = [i for i in range(0,mp.shape[0]-1) if mp[i+1,1] != mp[i,1] + 1]
    tolerance = int(window_size/2)
    variances = []

    #For each candidate change point, 
    # the code first computes the mean and standard deviation of the time series 
    # within two windows centered around the candidate point. 
    # The mean_change variable is then set to the absolute difference 
    # between the means of the two windows,
    #  while std_change is set to the absolute difference between 
    #  the standard deviations of the two windows. 
    #  The std_mean variable is set to the mean of the standard deviations 
    #  of the two windows.
    for idx in proposed_cp:
        mean_change = np.abs(np.mean(t[idx-tolerance:idx]) - np.mean(t[idx:idx+tolerance]))
        std_change = np.abs(np.std(t[idx-tolerance:idx]) - np.std(t[idx:idx+tolerance])) 
        std_mean = np.mean([np.std(t[idx-tolerance:idx]),np.std(t[idx:idx+tolerance])])
        variances.append(mean_change*std_change/std_mean)
    sorted_idx = np.flip(np.array(variances).argsort())#from largest to smallest
    sorted_cp = [proposed_cp[idx] for idx in sorted_idx]
    selected_cp = []
    covered = list(np.arange(0,tolerance)) #[0, 1, 2, 3, 4]
    ic, i = 0, 0 
    while ic < change_points: #change points are givven when function called. Right now it is int 3
        if i == len(sorted_cp):
            break
        if sorted_cp[i] not in covered:
            ic += 1
            selected_cp.append(sorted_cp[i])
            covered = covered + list(np.arange(sorted_cp[i],sorted_cp[i]+tolerance))
            covered = covered + list(np.arange(sorted_cp[i]-tolerance,sorted_cp[i]))
        i +=1 
    selected_cp = np.sort(np.asarray(selected_cp))

    # change_points is set to 3, so the function will return 3 change points. 
    # However, the actual number of change points returned may be less than 3
    # if there are not enough significant change points detected by the algorithm.

    return(list(selected_cp))

def backgroundIdentification(original_signal,f=40):

    # Background identification aims to isolate the non-periodic or non-transient components in a signal, 
    # which are considered to be the background or noise.
    # The background components can be removed from the signal or can be used to reconstruct
    # the signal by filtering out the background frequencies.

    f, t, Zxx = signal.stft(original_signal.reshape(original_signal.shape[0]),1,nperseg=f)
    frequency_composition_abs = np.abs(Zxx)
    measures = []
    for freq,freq_composition in zip(f,frequency_composition_abs):
        measures.append(np.mean(freq_composition)/np.std(freq_composition))
    max_value = max(measures)
    selected_frequency = measures.index(max_value)
    weights = 1-(measures/sum(measures))
    dummymatrix = np.zeros((len(f),len(t)))
    dummymatrix[selected_frequency,:] = 1  
    #Option to admit information from other frequency bands
    """dummymatrix = np.ones((len(f),len(t)))
    for i in range(0,len(weights)):
        dummymatrix[i,:] = dummymatrix[i,:] * weights[i]"""
    
    background_frequency = Zxx * dummymatrix
    _, xrec = signal.istft(background_frequency, 1)
    xrec = xrec[:original_signal.shape[0]]
    xrec = xrec.reshape(original_signal.shape)
    #xrec is a numpy array that contains the reconstructed signal after applying the background identification process.
    #It represents the background component of the original signal that was removed during the process.
    return xrec

def RBP(generated_samples_interpretable, original_signal, segment_indexes, f):

    #  RBP is a technique for modifying a signal by replacing certain segments with corresponding segments 
    #  the background signal. It is used to generate new samples that are similar to the original signal, 
    #  but with specific parts modified according to the output of an interpretable model.

  #segment  indices are what NNsagement returned
    generated_samples_raw = []

    # The RBP function first calls the backgroundIdentification function to identify and extract the non-periodic 
    # or non-transient components of the original signal. These components are considered to be the "background" of the signal, 
    # and are subtracted from the signal to leave only the interesting parts.

    xrec = backgroundIdentification(original_signal)
    for sample_interpretable in generated_samples_interpretable:
        raw_signal = original_signal.copy()

        # for each binary sequence in generated_samples_interpretable, the function creates a copy of original_signal,
        # and for each segment indicated by a 0 in the binary sequence, it replaces the values in the copy of the signal 
        # with the corresponding values in the background signal obtained from backgroundIdentification.

        for index in range(0,len(sample_interpretable)-1):
            if sample_interpretable[index] == 0:
                index0 = segment_indexes[index]
                index1 = segment_indexes[index+1]
                raw_signal[index0:index1] = xrec[index0:index1]
        generated_samples_raw.append(np.asarray(raw_signal))
    return np.asarray(generated_samples_raw)

def RBPIndividual(original_signal, index0, index1):
    xrec = backgroundIdentification(original_signal)
    raw_signal = original_signal.copy()
    raw_signal[index0:index1] = xrec[index0:index1]
    return raw_signal

def LIMESegment(example, model, model_type='class', distance='dtw', n=100, window_size=None, cp=None, f=None, random_state=None):
    random_state = check_random_state(random_state)
    if window_size is None:
        window_size =int(example.shape[0]/5)
    if cp is None:
        cp = 3
    if f is None: 
        f = int(example.shape[0]/10)
    #series.reshape(series.shape[0]) reshapes the time series to a 1-d array. (it was two)
    cp_indexes = NNSegment(example.reshape(example.shape[0]), window_size, cp)
    segment_indexes = [0] + cp_indexes + [-1]
    
    generated_samples_interpretable = [random_state.binomial(1, 0.5, len(cp_indexes)+1) for _ in range(0,n)] #Update here with random_state
    generated_samples_raw = RBP(generated_samples_interpretable, example, segment_indexes, f)
    sample_predictions = model.predict(generated_samples_raw)
    
    if model_type == 'proba':
        y_labels = np.argmax(sample_predictions, axis=1)
    elif isinstance(model_type, int): #Update here to use the probability of the target class
        y_labels = sample_predictions[:, model_type]
    else:
        y_labels = sample_predictions
    
    if distance == 'dtw':
        distances = np.asarray([fastdtw(example, sample)[0] for sample in generated_samples_raw])
        weights = np.exp(-(np.abs((distances - np.mean(distances))/np.std(distances)).reshape(n,)))
    elif distance == 'euclidean':
        distances = np.asarray([np.linalg.norm(np.ones(len(cp_indexes)+1)-x) for x in generated_samples_interpretable])
        weights = np.exp(-(np.abs(distances**2/0.75*(len(segment_indexes)**2)).reshape(n,)))
        
    clf = Ridge(random_state=random_state) #Update here with random_state
    clf.fit(generated_samples_interpretable,y_labels, weights)
    
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


