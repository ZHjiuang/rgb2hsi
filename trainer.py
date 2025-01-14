import os
import time
import datetime
import itertools
import numpy as np
import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.autograd as autograd
from torch.utils.data import DataLoader
import torch.backends.cudnn as cudnn
from tqdm import tqdm

import dataset
import utils


def Trainer(opt):
    # ----------------------------------------
    #       Network training parameters
    # ----------------------------------------

    # Handle multiple GPUs
    if opt.device != "cpu":
        device = torch.device("cuda")
        gpu_num = torch.cuda.device_count()
        print("There are %d GPUs:" % (gpu_num))
        opt.batch_size *= gpu_num
        opt.num_workers *= gpu_num
    else:
        device = torch.device("cpu")
    # Create folders
    save_model_folder = opt.data_type + '_' + opt.process_type + '_' + opt.network_type
    utils.check_path(save_model_folder)

    # cudnn benchmark
    if opt.device != "cpu":
        cudnn.benchmark = opt.cudnn_benchmark

    # Loss functions
    criterion_L1 = torch.nn.L1Loss()
    criterion_rSAD = utils.reconstruction_SADloss()
    criterion_FFL = utils.FocalFrequencyLoss()

    # Initialize SGN
    generator = utils.create_generator(opt)

    # To device
    if opt.device != "cpu":
        generator = nn.DataParallel(generator)
    generator = generator.to(device)

    # Optimizers
    optimizer_G = torch.optim.Adam(generator.parameters(), lr=opt.lr, betas=(opt.b1, opt.b2),
                                   weight_decay=opt.weight_decay)

    # Learning rate decrease
    def adjust_learning_rate(opt, epoch, iteration, optimizer):
        # Set the learning rate to the initial LR decayed by "lr_decrease_factor" every "lr_decrease_epoch" epochs
        if opt.lr_decrease_mode == 'epoch':
            lr = opt.lr * (opt.lr_decrease_factor ** (epoch // opt.lr_decrease_epoch))
            for param_group in optimizer.param_groups:
                param_group['lr'] = lr
        if opt.lr_decrease_mode == 'iter':
            lr = opt.lr * (opt.lr_decrease_factor ** (iteration // opt.lr_decrease_iter))
            for param_group in optimizer.param_groups:
                param_group['lr'] = lr

    # Save the model
    def save_model(opt, epoch, iteration, len_dataset, generator):
        # Define the name of trained model
        if opt.save_mode == 'epoch':
            model_name = 'G_epoch%d_bs%d.pth' % (epoch, opt.batch_size)
        if opt.save_mode == 'iter':
            model_name = 'G_iter%d_bs%d.pth' % (iteration, opt.batch_size)
        save_model_path = os.path.join(opt.save_path, model_name)
        # Save model
        if opt.save_mode == 'epoch':
            if (epoch % opt.save_by_epoch == 0) and (iteration % len_dataset == 0):
                torch.save(generator.module.state_dict(), save_model_path)
                # print('The trained model is successfully saved at epoch %d' % (epoch))
        if opt.save_mode == 'iter':
            if iteration % opt.save_by_iter == 0:
                torch.save(generator.module.state_dict(), save_model_path)
                # print('The trained model is successfully saved at iteration %d' % (iteration))

    # ----------------------------------------
    #             Network dataset
    # ----------------------------------------

    # Define the dataset
    trainset = utils.create_dataset(opt)
    print('The overall number of images:', len(trainset))

    # Define the dataloader
    dataloader = DataLoader(trainset, batch_size=opt.batch_size, shuffle=True, num_workers=opt.num_workers,
                            pin_memory=True)

    # ----------------------------------------
    #                 Training
    # ----------------------------------------

    # Count start time
    prev_time = time.time()

    # For loop training
    for epoch in range(opt.epochs):
        train_bar = tqdm(dataloader)
        for i, (img_A, img_B) in enumerate(train_bar):
            # To device
            img_A = img_A.to(device)
            img_B = img_B.to(device)

            # Train Generator
            optimizer_G.zero_grad()

            # Forword propagation
            recon_B = generator(img_A)

            # Losses
            l1loss = criterion_L1(recon_B, img_B)
            rsadloss = criterion_rSAD(recon_B, img_B)
            ffloss = criterion_FFL(recon_B, img_B)
            loss = l1loss + 0.1 * rsadloss + 0.001 * ffloss

            # Overall Loss and optimize
            loss.backward()
            optimizer_G.step()

            # Determine approximate time left
            iters_done = epoch * len(dataloader) + i
            iters_left = opt.epochs * len(dataloader) - iters_done
            time_left = datetime.timedelta(seconds=iters_left * (time.time() - prev_time))
            prev_time = time.time()

            # Print log
            train_bar.set_description(f'Epoch [{epoch}/{opt.epochs}]')
            train_bar.set_postfix(loss=loss.item())

            # Save model at certain epochs or iterations
            save_model(opt, (epoch + 1), (iters_done + 1), len(dataloader), generator)

            # Learning rate decrease at certain epochs
            adjust_learning_rate(opt, (epoch + 1), (iters_done + 1), optimizer_G)


def Trainer_GAN(opt):
    # ----------------------------------------
    #       Network training parameters
    # ----------------------------------------

    # Handle multiple GPUs
    if opt.device != "cpu":
        device = torch.device("cuda")
        gpu_num = torch.cuda.device_count()
        print("There are %d GPUs:" % (gpu_num))
        opt.batch_size *= gpu_num
        opt.num_workers *= gpu_num
    else:
        device = torch.device("cpu")
    # Create folders
    save_model_folder = opt.data_type + '_' + opt.process_type + '_' + opt.network_type
    utils.check_path(save_model_folder)

    # cudnn benchmark
    if opt.device != "cpu":
        cudnn.benchmark = opt.cudnn_benchmark

    # Loss functions
    criterion_L1 = torch.nn.L1Loss().to(device)
    criterion_rSAD = utils.reconstruction_SADloss()
    criterion_FFL = utils.FocalFrequencyLoss()

    # Initialize SGN
    generator = utils.create_generator(opt)
    discriminator = utils.create_discriminator(opt)

    # To device
    if opt.device != "cpu":
        generator = nn.DataParallel(generator)
        discriminator = nn.DataParallel(discriminator)

    generator = generator.to(device)
    discriminator = discriminator.to(device)

    # Optimizers
    optimizer_G = torch.optim.Adam(generator.parameters(), lr=opt.lr, betas=(opt.b1, opt.b2),
                                   weight_decay=opt.weight_decay)
    optimizer_D = torch.optim.Adam(discriminator.parameters(), lr=opt.lr, betas=(opt.b1, opt.b2))

    # Learning rate decrease
    def adjust_learning_rate(opt, epoch, iteration, optimizer):
        # Set the learning rate to the initial LR decayed by "lr_decrease_factor" every "lr_decrease_epoch" epochs
        if opt.lr_decrease_mode == 'epoch':
            lr = opt.lr * (opt.lr_decrease_factor ** (epoch // opt.lr_decrease_epoch))
            for param_group in optimizer.param_groups:
                param_group['lr'] = lr
        if opt.lr_decrease_mode == 'iter':
            lr = opt.lr * (opt.lr_decrease_factor ** (iteration // opt.lr_decrease_iter))
            for param_group in optimizer.param_groups:
                param_group['lr'] = lr

    # Save the model
    def save_model(opt, epoch, iteration, len_dataset, generator):
        # Define the name of trained model
        if opt.save_mode == 'epoch':
            model_name = 'G_GAN_epoch%d_bs%d.pth' % (epoch, opt.batch_size)
        if opt.save_mode == 'iter':
            model_name = 'G_GAN_iter%d_bs%d.pth' % (iteration, opt.batch_size)
        save_model_path = os.path.join(save_model_folder, model_name)
        # Save model
        if opt.save_mode == 'epoch':
            if (epoch % opt.save_by_epoch == 0) and (iteration % len_dataset == 0):
                torch.save(generator.module.state_dict(), save_model_path)
                # print('The trained model is successfully saved at epoch %d' % (epoch))
        if opt.save_mode == 'iter':
            if iteration % opt.save_by_iter == 0:
                torch.save(generator.module.state_dict(), save_model_path)
                # print('The trained model is successfully saved at iteration %d' % (iteration))
    # ----------------------------------------
    #             Network dataset
    # ----------------------------------------

    # Define the dataset
    trainset = utils.create_dataset(opt)
    print('The overall number of images:', len(trainset))

    # Define the dataloader
    dataloader = DataLoader(trainset, batch_size=opt.batch_size, shuffle=True, num_workers=opt.num_workers,
                            pin_memory=True)

    # ----------------------------------------
    #                 Training
    # ----------------------------------------

    # Count start time
    prev_time = time.time()

    # For loop training
    for epoch in range(opt.epochs):
        train_bar = tqdm(dataloader)
        for i, (img_A, img_B) in enumerate(train_bar):
            # To device
            img_A = img_A.to(device)
            img_B = img_B.to(device)

            # Initialize optimizers
            optimizer_G.zero_grad()
            optimizer_D.zero_grad()

            # Train Discriminator
            # Forword propagation
            recon_B = generator(img_A)

            # GAN Loss
            # Fake samples
            fake_scalar_d = discriminator(recon_B.detach())
            # True samples
            true_scalar_d = discriminator(img_B)
            # Overall Loss and optimize
            loss_D = - torch.mean(true_scalar_d) + torch.mean(fake_scalar_d)
            loss_D.backward()
            optimizer_D.step()

            # Train Generator
            # Forword propagation
            recon_B = generator(img_A)

            fake_scalar = discriminator(recon_B)
            loss_G = - torch.mean(fake_scalar)

            # Losses
            L1Loss = criterion_L1(recon_B, img_B)
            l1loss = criterion_L1(recon_B, img_B)
            rsadloss = criterion_rSAD(recon_B, img_B)
            ffloss = criterion_FFL(recon_B, img_B)
            img_loss = l1loss + 0.1 * rsadloss + 0.001 * ffloss

            # Overall Loss and optimize
            loss = img_loss + opt.lambda_GAN * loss_G
            loss.backward()
            optimizer_G.step()

            # Determine approximate time left
            iters_done = epoch * len(dataloader) + i
            iters_left = opt.epochs * len(dataloader) - iters_done
            time_left = datetime.timedelta(seconds=iters_left * (time.time() - prev_time))
            prev_time = time.time()

            # Print log
            train_bar.set_description(f'Epoch [{epoch}/{opt.epochs}]')
            train_bar.set_postfix(loss=loss.item(), l1loss=img_loss.item(), loss_G=loss_G.item())

            # Save model at certain epochs or iterations
            save_model(opt, (epoch + 1), (iters_done + 1), len(dataloader), generator)

            # Learning rate decrease at certain epochs
            adjust_learning_rate(opt, (epoch + 1), (iters_done + 1), optimizer_G)
