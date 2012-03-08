# Copyright (c) 2012 Sergey Danielyan a.k.a gahcep
# 
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

from Queue import Queue
from threading import Event, Thread
from time import time, gmtime, strftime

## Limits
PRECISION_MIN               = 0.001
PRECISION_DEFAULT           = 0.001
PRECISION_MAX               = 1
TIMER_INTERVAL_MIN          = 0
TIMER_INTERVAL_MAX          = 3600
TIMER_INTERVAL_INITIAL_MIN  = 1 
TIMER_INTERVAL_INITIAL_MAX  = 3600
TIMER_COUNT_MIN             = 0
TIMER_COUNT_MAX             = 10000
SUSPENDED_DELAY_MIN         = 0
SUSPENDED_DELAY_MAX         = 10000
TIMER_QUEUE_SIZE            = 100

## Timer activation options
TIMER_ACTIVATE              = 1
TIMER_NO_ACTIVATE           = 0

## State definitions
TIMER_STATE_IDLE            = 1
TIMER_STATE_INIT            = 2
TIMER_STATE_RUNNINGINITIAL  = 3
TIMER_STATE_RUNNING         = 4
TIMER_STATE_SUSPENDED       = 5
TIMER_STATE_TERMINATED      = 6

## For translate state numerical code
STATE_TO_TEXT = {
1 : 'TIMER_STATE_IDLE',
2 : 'TIMER_STATE_INIT',
3 : 'TIMER_STATE_RUNNINGINITIAL',
4 : 'TIMER_STATE_RUNNING',
5 : 'TIMER_STATE_SUSPENDED',
6 : 'TIMER_STATE_TERMINATED',
}

## Message types
MESSAGE_INIT                = 100
MESSAGE_ACTIVATE            = 101
MESSAGE_DEACTIVATE          = 102
MESSAGE_PAUSE               = 103
MESSAGE_RESUME              = 104
MESSAGE_CHANGE              = 105
MESSAGE_TERMINATE           = 106
MESSAGE_PRECISION           = 107

## Error codes
T_SUCCESS                   = 1000
T_ERROR_INCORRECT_STATE     = 1001
T_ERROR_ALREADY_SWITCHED    = 1002

## Experimental #####################

## Function result conditions
T_IS_FUNC_RESULT_TRUE       = 1
T_IS_FUNC_RESULT_FALSE      = 2
T_IS_FUNC_RESULT_OF_TYPE    = 3
T_IS_FUNC_RESULT_OF_VALUE   = 4

## Function behaviour types
T_BEHAV_TIMER_TERMINATED    = 1
T_BEHAV_TIMER_DEACTIVATED   = 2
T_BEHAV_TIMER_PAUSE         = 3


class WaitableTimer(Thread):
    
    def __init__(self, 
                 TimerInitialInterval, TimerContinuousInterval,
                 FunctionProc,
                 StartCondition = TIMER_ACTIVATE, 
                 TimerCount = TIMER_COUNT_MIN, 
                 Precision = PRECISION_DEFAULT,
                 DEBUG = False,
                 PROFILE = False,
                 FunctionArgs = [], FunctionKWArgs = {}
                 ):
        
        ## Had to be the first
        Thread.__init__(self)
        
        # Received parameters 
        self.ValidatePrecision(Precision)
        self.ValidateInitialInterval(TimerInitialInterval)
        self.ValidateInterval(TimerContinuousInterval)
        self.ValidateCount(TimerCount)
        ## Function related
        self.__FunctionProc = FunctionProc
        self.__FunctionArgs = FunctionArgs
        self.__FunctionKWArgs = FunctionKWArgs
        ## Debug related
        self.__DEBUG = DEBUG 
        self.__PROFILE = PROFILE
        ## Flags        
        self.__IsOneTimeShotTimer = True if self.__TimerInterval == 0 else False
        self.__IsRepeatableTimer = True if self.__TimerCount != 0 else False
        
        # Inner variables
        self.__SuspendedDelay = 0
        self.__State = TIMER_STATE_IDLE
        self.__Error = T_SUCCESS 
        
        # Events
        self.__ePauseResume = Event()
        self.__eActivate = Event()
        self.__eDeactivate = Event()
        self.__eInit = Event()
        self.__eTerminate = Event()
        
        # Queue init
        self.__MsgQueue = Queue(TIMER_QUEUE_SIZE)
        
        # Move to first working state
        self.__MsgQueue.put_nowait((MESSAGE_INIT, 0, 0))
        
        # Or even further
        if StartCondition == TIMER_ACTIVATE:
            self.__MsgQueue.put_nowait((MESSAGE_ACTIVATE, 0, 0))
    
    def run(self):        
        
        ## Variables for saving/restoring values
        SavedState = TIMER_STATE_IDLE
        SavedTime = 0
        
        ## Working variables
        InitialTime = 0
        TimeoutMark = 0
                
        ## Main cycle
        while not self.__eTerminate.is_set():
            
            ##################################
            ##### Message Processing Loop ####
            ##################################
            while not self.__MsgQueue.empty():
                message = self.__MsgQueue.get_nowait()
                
                ## MESSAGE_INIT
                if message[0] == MESSAGE_INIT:
                    self.__DebugPrint(">> Received MESSAGE_INIT")
                    self.__eInit.set()                    
                
                ## MESSAGE_CHANGE
                elif message[0] == MESSAGE_CHANGE:
                    self.__DebugPrint(">> Received MESSAGE_CHANGE")
                    self.ValidateInitialInterval(message[1])
                    self.ValidateInterval(message[2])
                    
                    if self.__State == TIMER_STATE_RUNNINGINITIAL:
                        TimeoutMark += self.__TimerInitialInterval - TimeoutMark
                    elif self.__State == TIMER_STATE_RUNNING:
                        TimeoutMark += self.__TimerInterval - TimeoutMark
                
                ## MESSAGE_PRECISION
                elif message[0] == MESSAGE_PRECISION:
                    self.__DebugPrint(">> Received MESSAGE_PRECISION")
                    self.ValidatePrecision(message[1])
                
                ## MESSAGE_ACTIVATE
                elif message[0] == MESSAGE_ACTIVATE:
                    self.__DebugPrint(">> Received MESSAGE_ACTIVATE")
                    self.__eActivate.set()
                    
                ## MESSAGE_DEACTIVATE
                elif message[0] == MESSAGE_DEACTIVATE:
                    self.__DebugPrint(">> Received MESSAGE_DEACTIVATE")
                    self.__eDeactivate.set()
                    
                ## MESSAGE_PAUSE
                elif message[0] == MESSAGE_PAUSE:
                    self.__DebugPrint(">> Received MESSAGE_PAUSE")
                    self.__ePauseResume.set()
                    self.ValidateDelay(message[1])
                    
                ## MESSAGE_RESUME
                elif message[0] == MESSAGE_RESUME:
                    self.__DebugPrint(">> Received MESSAGE_RESUME")
                    self.__ePauseResume.set()
                    self.__SuspendedDelay = 0
                
                ## MESSAGE_TERMINATE
                elif message[0] == MESSAGE_TERMINATE:
                    self.__DebugPrint(">> Received MESSAGE_TERMINATE")
                    self.__eTerminate.set()
            
            ##################################
            ##### State Processing Loop ######
            ##################################
            
            ## TIMER_STATE_IDLE 
            if self.__State == TIMER_STATE_IDLE:
                self.__DebugPrint("Current State: TIMER_STATE_IDLE")
                if self.__eInit.is_set():
                    self.__DebugPrint("Changing the state to TIMER_STATE_INIT")
                    self.__State = TIMER_STATE_INIT
                    self.__eInit.clear()
                    continue
            
            ## TIMER_STATE_INIT
            elif self.__State == TIMER_STATE_INIT:
                self.__DebugPrint("Current State: TIMER_STATE_INIT")
                
                if self.__eActivate.is_set():
                    self.__DebugPrint("Changing the state to TIMER_STATE_RUNNINGINITIAL")
                    self.__State = TIMER_STATE_RUNNINGINITIAL
                    self.__eActivate.clear()
                    TimeoutMark = self.__TimerInitialInterval
                    InitialTime = time()
                    continue
            
            ## TIMER_STATE_SUSPENDED
            elif self.__State == TIMER_STATE_SUSPENDED:
                self.__DebugPrint("Current State: TIMER_STATE_SUSPENDED")
                if self.__eTerminate.is_set():
                    self.__DebugPrint("Terminating a timer")
                    continue
                
                if self.__eDeactivate.is_set():
                    self.__DebugPrint("Changing the state to TIMER_STATE_INIT")
                    self.__eDeactivate.clear()
                    self.__State = TIMER_STATE_INIT
                    continue
                
                if self.__ePauseResume.is_set():
                    self.__DebugPrint("Restoring the state after Pause()")
                    self.__State = SavedState
                    # Increase the initial value with the value of delay
                    # "time() - SavedTime" - amount of delay 
                    InitialTime += time() - SavedTime
                    self.__ePauseResume.clear()
                    continue
                
                if self.__SuspendedDelay != 0:
                    if (time() - SavedTime) >= self.__SuspendedDelay:
                        self.__DebugPrint("SuspendedDelay is over now")
                        # Automatically check in the flag if delay is over
                        self.__ePauseResume.set()
                        continue

            ## TIMER_STATE_RUNNINGINITIAL
            elif self.__State == TIMER_STATE_RUNNINGINITIAL:
                self.__DebugPrint("Current State: TIMER_STATE_RUNNINGINITIAL")
                # Preinitial processing due to immediately exit from the cycle
                # ignoring the fact, that FunctionProc might be just invoked 
                if self.__eTerminate.is_set():
                    self.__DebugPrint("Terminating a timer")
                    continue
                
                if self.__eDeactivate.is_set():
                    self.__DebugPrint("Changing the state to TIMER_STATE_INIT")
                    self.__eDeactivate.clear()
                    self.__State = TIMER_STATE_INIT
                    continue
                
                if self.__ePauseResume.is_set():
                    self.__DebugPrint("Changing the state to TIMER_STATE_SUSPENDED")
                    SavedState = self.__State
                    SavedTime = time()
                    self.__State = TIMER_STATE_SUSPENDED
                    self.__ePauseResume.clear()
                    continue
                
                if (time() - InitialTime) >= TimeoutMark:
                    self.__DebugPrint("Invoking a FUNCTION")
                    self.__State = TIMER_STATE_RUNNING
                    # Behaviour logic
                    FResult = self.__FunctionProc(*self.__FunctionArgs, **self.__FunctionKWArgs)
                    #if self.__FunctionResult = True
                    TimeoutMark = self.__TimerInterval
                    InitialTime = time()
                    if self.__IsOneTimeShotTimer:
                        self.__DebugPrint("Terminating a One-Time-Shot timer")
                        self.__eTerminate.set()
                    continue
                
            ## TIMER_STATE_RUNNING
            elif self.__State == TIMER_STATE_RUNNING:
                self.__DebugPrint("Current State: TIMER_STATE_RUNNING")
                # Preinitial processing due to immediately exit from the cycle
                # ignoring the fact, that FunctionProc might be just invoked 
                if self.__eTerminate.is_set():
                    self.__DebugPrint("Terminating a timer")
                    continue
                
                if self.__eDeactivate.is_set():
                    self.__DebugPrint("Changing the state to TIMER_STATE_INIT")
                    self.__eDeactivate.clear()
                    self.__State = TIMER_STATE_INIT
                    continue
                
                if self.__ePauseResume.is_set():
                    self.__DebugPrint("Changing the state to TIMER_STATE_SUSPENDED")
                    SavedState = self.__State
                    SavedTime = time()
                    self.__State = TIMER_STATE_SUSPENDED
                    self.__ePauseResume.clear()
                    continue
                
                if (time() - InitialTime) >= TimeoutMark:
                    self.__DebugPrint("Invoking a FUNCTION")
                    self.__FunctionProc(*self.__FunctionArgs, **self.__FunctionKWArgs)
                    InitialTime = time()
                    if self.__IsRepeatableTimer:
                        self.__TimerCount -= 1
                        if (self.__TimerCount <= 0):
                            self.__DebugPrint("Terminating a Repeatable timer")
                            self.__eTerminate.set()
                            continue
                        else:
                            self.__DebugPrint("Remained invocation function calls: " + repr(self.__TimerCount))
            
            if not self.__eTerminate.is_set():
                self.__DebugPrint("Terminating a timer")
                self.__eTerminate.wait(self.__Precision)

        self.__State = TIMER_STATE_TERMINATED
        self.__DebugPrint("Current State: TIMER_STATE_TERMINATED")
    
    ############ Decorator ##############
    def Validate(Minimum, Maximum):
        ## Dynamically creating a decorator 
        def Decorator(Function):
            ## Function to call
            def WrapFunction(self, Value):
                Value = Minimum if Value < Minimum else Maximum if Value > Maximum else Value
                ## Function invocation
                Function(self, Value)
            return WrapFunction
        return Decorator
    
    ########### Validators ################
    @Validate(TIMER_INTERVAL_INITIAL_MIN, TIMER_INTERVAL_INITIAL_MAX)
    def ValidateInitialInterval(self, Value):
        self.__TimerInitialInterval = Value
    
    @Validate(TIMER_INTERVAL_MIN, TIMER_INTERVAL_MAX)
    def ValidateInterval(self, Value):
        self.__TimerInterval = Value
    
    @Validate(PRECISION_MIN, PRECISION_MAX)
    def ValidatePrecision(self, Value):
        self.__Precision = Value
    
    @Validate(TIMER_COUNT_MIN, TIMER_COUNT_MAX)
    def ValidateCount(self, Value):
        self.__TimerCount = Value
            
    @Validate(SUSPENDED_DELAY_MIN, SUSPENDED_DELAY_MAX)
    def ValidateDelay(self, Value):
        self.__SuspendedDelay = Value
        
    ########## Getter/Setter functions #########
    def GetPrecision(self):
        return self.__Precision                
    
    def GetState(self):
        return self.__State
    
    def GetError(self):
        return self.__Error
    
    ########### Output Debug information ##########
    def __OutputErrorState(self, RequiredTimerState = [], Invert=False):
        PrintString = "Error: wrong state: should be "
        CondCount = len(RequiredTimerState)
        if not Invert:
            for index, nextstate in enumerate(RequiredTimerState):
                PrintString += STATE_TO_TEXT[nextstate]
                if index != (CondCount - 1): PrintString += " or "
            PrintString += " instead of "
            PrintString += STATE_TO_TEXT[self.__State]
        else:
            PrintString += "anything except of "
            PrintString += STATE_TO_TEXT[RequiredTimerState[0]]
        return PrintString
    
    def __DebugPrint(self, Message):
        if self.__DEBUG:
            if self.__PROFILE: 
                print strftime("[%H:%M:%S.", gmtime()) + (("%.3f" % time()).split("."))[1] + "]\t",
            print Message
    
    ########## Behaviour functions ###########
    def SetChange(self, Initial, Interval):
        self.__DebugPrint("SetChange(): In function")
        
        if self.__State != TIMER_STATE_TERMINATED:
            self.__MsgQueue.put_nowait((MESSAGE_CHANGE, Initial, Interval))
            self.__DebugPrint("SetChange(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        else:
            self.__DebugPrint("SetChange(): " + self.__OutputErrorState([TIMER_STATE_TERMINATED], Invert=True))
            self.__Error = T_ERROR_INCORRECT_STATE
            return False
    
    def SetPrecision(self, Precision):
        self.__DebugPrint("SetPrecision(): In function")
        
        if self.__State != TIMER_STATE_TERMINATED:
            self.__MsgQueue.put_nowait((MESSAGE_PRECISION, Precision, 0))
            self.__DebugPrint("SetPrecision(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        else:
            self.__DebugPrint("SetPrecision(): " + self.__OutputErrorState([TIMER_STATE_TERMINATED], Invert=True))
            self.__Error = T_ERROR_INCORRECT_STATE
            return False
    
    ## EXPERIMENTAL ##########################
    def SetTimerFuncBehaviour(self, FunctionResult, FunctionAction, 
                              FunctionType = None, FunctionValue = None):
        self.__DebugPrint("SetTimerFuncBehaviour(): In function")
        
        # There is no any DisableStateCheck flag, so it has to be a right state - INIT
        if self.__State != TIMER_STATE_INIT:
            self.__DebugPrint("SetTimerFuncBehaviour(): " + self.__OutputErrorState([TIMER_STATE_INIT], Invert=True))
            self.__Error = T_ERROR_INCORRECT_STATE
            return False
        else:
            self.__FunctionResult = FunctionResult
            self.__FunctionAction = FunctionAction
            self.__FunctionType = FunctionType
            self.__FunctionValue = FunctionValue
    
    ########## Action functions ##############
    def Activate(self, DisableStateCheck = False):
        self.__DebugPrint("Activate(): In function")
        
        if DisableStateCheck:
            self.__MsgQueue.put_nowait((MESSAGE_ACTIVATE, 0, 0))
            self.__DebugPrint("Activate(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        
        elif (self.__State == TIMER_STATE_RUNNING) or (self.__State == TIMER_STATE_RUNNINGINITIAL):
            self.__DebugPrint("Activate(): Warning: already in RUNNING mode")
            self.__Error = T_ERROR_ALREADY_SWITCHED
            return False
        
        elif (self.__State == TIMER_STATE_INIT) or (self.__State == TIMER_STATE_IDLE):
            self.__MsgQueue.put_nowait((MESSAGE_ACTIVATE, 0, 0))
            self.__DebugPrint("Activate(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        else:
            self.__DebugPrint("Activate(): " + self.__OutputErrorState([TIMER_STATE_INIT, TIMER_STATE_IDLE]))
            self.__Error = T_ERROR_INCORRECT_STATE
            return False
    
    def Pause(self, Wait=0, DisableStateCheck = False):
        self.__DebugPrint("Pause(): In function")
        
        if DisableStateCheck:
            self.__MsgQueue.put_nowait((MESSAGE_PAUSE, Wait, 0))
            self.__DebugPrint("Pause(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        
        elif self.__State == TIMER_STATE_SUSPENDED:
            self.__DebugPrint("Pause(): Warning: already in SUSPENDED mode")
            self.__Error = T_ERROR_ALREADY_SWITCHED
            return False
        
        elif (self.__State == TIMER_STATE_RUNNINGINITIAL) or (self.__State == TIMER_STATE_RUNNING):
            self.__MsgQueue.put_nowait((MESSAGE_PAUSE, Wait, 0))
            self.__DebugPrint("Pause(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        else:
            self.__DebugPrint("Pause(): " + self.__OutputErrorState([TIMER_STATE_RUNNINGINITIAL, TIMER_STATE_RUNNING]))
            self.__Error = T_ERROR_INCORRECT_STATE
            return False
    
    def Resume(self, DisableStateCheck = False):
        
        self.__DebugPrint("Resume(): In function")
        
        if DisableStateCheck:
            self.__MsgQueue.put_nowait((MESSAGE_RESUME, 0, 0))
            self.__DebugPrint("Resume(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        
        elif (self.__State == TIMER_STATE_RUNNINGINITIAL) or (self.__State == TIMER_STATE_RUNNING):
            self.__DebugPrint("Resume(): Warning: already in RUNNING mode")
            self.__Error = T_ERROR_ALREADY_SWITCHED
            return False
        
        elif self.__State == TIMER_STATE_SUSPENDED:
            self.__MsgQueue.put_nowait((MESSAGE_RESUME, 0, 0))
            self.__DebugPrint("Resume(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        else:
            self.__DebugPrint("Resume(): " + self.__OutputErrorState([TIMER_STATE_SUSPENDED]))
            self.__Error = T_ERROR_INCORRECT_STATE
            return False
    
    def Deactivate(self, DisableStateCheck = False):
        
        self.__DebugPrint("Deactivate(): In function")
        
        if DisableStateCheck:
            self.__MsgQueue.put_nowait((MESSAGE_DEACTIVATE, 0, 0))
            self.__DebugPrint("Deactivate(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        
        elif self.__State == TIMER_STATE_INIT:
            self.__DebugPrint("Deactivate(): Warning: already in INIT mode")
            self.__Error = T_ERROR_ALREADY_SWITCHED
            return False
        
        elif (self.__State == TIMER_STATE_SUSPENDED) or (self.__State == TIMER_STATE_RUNNING) or (self.__State == TIMER_STATE_RUNNINGINITIAL):
            self.__MsgQueue.put_nowait((MESSAGE_DEACTIVATE, 0, 0))
            self.__DebugPrint("Deactivate(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        else:
            self.__DebugPrint("Deactivate(): " + self.__OutputErrorState([TIMER_STATE_SUSPENDED, TIMER_STATE_RUNNING, TIMER_STATE_RUNNINGINITIAL]))
            self.__Error = T_ERROR_INCORRECT_STATE
            return False
    
    def Terminate(self, DisableStateCheck = False):
        self.__DebugPrint("Terminate(): In function")
        
        ## Don't merge with next condition due to clarity
        if DisableStateCheck:
            self.__MsgQueue.put_nowait((MESSAGE_TERMINATE, 0, 0))
            self.__DebugPrint("Terminate(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        
        elif self.__State != TIMER_STATE_IDLE:
            self.__MsgQueue.put_nowait((MESSAGE_TERMINATE, 0, 0))
            self.__DebugPrint("Terminate(): Notice: message is sent")
            self.__Error = T_SUCCESS
            return True
        else:
            self.__DebugPrint(">> Terminate(): " + self.__OutputErrorState([TIMER_STATE_IDLE], Invert=True))
            self.__Error = T_ERROR_INCORRECT_STATE
            return False
