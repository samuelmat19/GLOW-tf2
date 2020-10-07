from common_definitions import *
from pipeline import *
from tqdm import tqdm
import matplotlib.pyplot as plt

if __name__ == "__main__":
    # Step 1. the data, split between train and test sets
    (x_train, y_train), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

    x_train = x_train.reshape(x_train.shape[0], IMG_SIZE, IMG_SIZE, CHANNEL_SIZE)
    x_test = x_test.reshape(x_test.shape[0], IMG_SIZE, IMG_SIZE, CHANNEL_SIZE)

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')

    # bounding space
    x_test = (ALPHA_BOUNDARY + (1 - ALPHA_BOUNDARY) * x_test / 255.)

    datagen = tf.keras.preprocessing.image.ImageDataGenerator(
        rotation_range=20,
        width_shift_range=0.05,
        height_shift_range=0.05,
        # horizontal_flip=True,
        shear_range=0.05)

    # # convert class vectors to binary class matrices
    # NUM_CLASSES = 10
    # y_train = tf.keras.utils.to_categorical(y_train, NUM_CLASSES)
    # y_test = tf.keras.utils.to_categorical(y_test, NUM_CLASSES)

    # filter to train
    x_train = x_train[y_train==3]
    y_train = y_train[y_train==3]
    x_test = x_test[y_test==3]
    y_test = y_test[y_test==3]

    def random_transform(x):
        x = datagen.random_transform(x)
        x = (ALPHA_BOUNDARY + (1 - ALPHA_BOUNDARY) * x / 255.)
        return x

    def augment(x,y):
        return (tf.reshape(tf.numpy_function(random_transform, inp=[x], Tout=tf.float32), (IMG_SIZE,IMG_SIZE,CHANNEL_SIZE)), y)

    train_dataset = tf.data.Dataset.from_tensor_slices((x_train, y_train))\
        .shuffle(SHUFFLE_SIZE)\
        .map(augment, num_parallel_calls=tf.data.experimental.AUTOTUNE)\
        .batch(BATCH_SIZE)\
        .prefetch(tf.data.experimental.AUTOTUNE)

    # Step 2. the brain
    brain = Brain(SQUEEZE_FACTOR, K_GLOW, L_GLOW, IMG_SIZE, LEARNING_RATE)

    # # load weight if available
    # print(brain.load_weights(CHECKPOINT_PATH))

    # Step 3. training iteration

    # define metrics variables
    nll = tf.keras.metrics.Mean("nll")
    mean_z_squared = tf.keras.metrics.Mean("mean_z_squared")
    var_z = tf.keras.metrics.Mean("var_z")
    test_img = x_test[0][None,:]
    test_img_2 = x_test[1][None,:]
    test_z = np.random.normal(0, 1, (1, IMG_SIZE * IMG_SIZE * CHANNEL_SIZE))

    # prepare for plt image results output
    if not os.path.exists("./results"):
        os.makedirs("./results")
    plt.imsave("./results/test_ref.png", np.squeeze(test_img))
    plt.imsave("./results/test_ref2.png", np.squeeze(test_img_2))

    # TENSORBOARD
    current_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    train_log_dir = TENSORBOARD_LOGDIR + current_time + '/train'
    train_summary_writer = tf.summary.create_file_writer(train_log_dir)

    _toggle_training = False
    for ep in range(EPOCHS):
        print(f"epoch {ep+1}/{EPOCHS}")
        nll.reset_states()
        mean_z_squared.reset_states()
        var_z.reset_states()
        
        # iteration per epoch
        with tqdm(train_dataset) as t:
            for x_t, y_t in t:
                # print(tf.reduce_min(x_t), tf.reduce_max(x_t))
                # plt.imshow(np.squeeze(x_t[0].numpy()))
                # plt.show()
                if _toggle_training:
                    z, _nll_x = brain.train_step(x_t)  # run the train step and store the nll in the variable
                    mean_z_squared(tf.reduce_mean(z, axis=-1)**2)
                    var_z(tf.math.reduce_variance(z, axis=-1))
                    nll(_nll_x)
                    t.set_postfix(nll=nll.result().numpy(), mean_sq=mean_z_squared.result().numpy(), var=var_z.result().numpy())
                else:  # to initiate some variables necessary
                    brain.model(x_t, training=True)
                    _toggle_training = True

        # save weight every epoch
        brain.save_weights(CHECKPOINT_PATH)

        # TENSORBOARD Save
        with train_summary_writer.as_default():
            tf.summary.scalar('nll', nll.result(), step=ep)
            tf.summary.scalar('mean_sq', mean_z_squared.result(), step=ep)
            tf.summary.scalar('var', var_z.result(), step=ep)
            tf.summary.image("inverted", tf.clip_by_value(brain.backward(brain.forward(test_img)), 0, 1), step=ep)
            tf.summary.image("from_random_07", tf.clip_by_value(brain.sample(temp=0.7), 0, 1), step=ep)

        # store image for evaluation
        plt.imsave("./results/test.png", tf.clip_by_value(tf.squeeze(brain.backward(
                    (brain.forward(test_img) + brain.forward(test_img_2)) / 2)), 0, 1).numpy())
        plt.imsave("./results/test2.png", tf.clip_by_value(tf.squeeze(brain.backward(test_z)), 0, 1).numpy())
        plt.imsave("./results/test3.png", tf.clip_by_value(tf.squeeze(brain.backward(
                    (brain.forward(test_img)))), 0, 1).numpy())
        plt.imsave("./results/test4.png", tf.clip_by_value(tf.squeeze(brain.sample(1.)), 0, 1).numpy())
        plt.imsave("./results/test5.png", tf.clip_by_value(tf.squeeze(brain.sample(0.2)), 0, 1).numpy())
