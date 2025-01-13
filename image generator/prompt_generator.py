import boto3
import json
import logging
import time
from botocore.exceptions import ClientError
from botocore.config import Config

from json import JSONDecodeError
import re

def parse(pattern:str, text: str) -> str:
    match = re.search(pattern, text, re.DOTALL)
    if match:
        text = match.group(1)
        return text.strip()
    else:
        raise JSONDecodeError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def generate_enhanced_prompt(task, description, max_retries=3, initial_delay=1):
    """
    Use Nova Pro to enhance a description into a better image generation prompt
    
    Args:
        description (str): The original scene description
        
    Returns:
        str: Enhanced prompt optimized for image generation
    """
    try:
        # Create Bedrock Runtime client with extended timeout
        bedrock = boto3.client(
            service_name='bedrock-runtime',
            config=Config(read_timeout=300)
        )
        if task =='text-to-image':
        # System instructions
            system_instructions = [{"text":"""
You are a Prompt Rewriting Expert for text-to-image models, with extensive knowledge in photography and Chinese Classical panting.
You specialize in helping users improve their text prompts according to specific rules to achieve better model outputs, sometimes modifying the original intent if necessary. 

##You excel in the following areas:##
Comprehensive understanding of the world, physical laws, and various interactive video scenarios
Rich imagination to visualize perfect, visually striking video scenes from simple prompts
Extensive film industry expertise as a master director, capable of enhancing simple video descriptions with optimal cinematography and visual effects

##Your prompt rewriting should follow these guidelines:##
- Prompting for image generation models differs from prompting for large language models (LLMs). Image generation models do not have the ability to reason or interpret explicit commands. Therefore, it's best to phrase your prompt as if it were an image caption rather than a command or conversation.You might want to include details about the subject, action, environment, lighting, style, and camera position.
- Consider adding modifiers like aspect ratios, image quality settings, or post-processing instructions to refine the output.
- Avoid topics such as pornography, racial discrimination, and toxic words.
- Be concise and less then 90 words.
- Do not use any Amazon Bedrock filter words, such as human names.
- Do not use negation words like "no", "not", "without", and so on in your prompt. The model doesn't understand negation in a prompt and attempting to use negation will result in the opposite of what you intend. For example, a prompt such as "a fruit basket with no bananas" will actually signal the model to include bananas. Instead, you can use a negative prompt, via the negative prompt, to specify any objects or characteristics that you want to exclude from the image. For example "bananas".
- An effective prompt often includes short descriptions of...
1. the subject
2. the environment
3. the main visual style is Chinese style
4. (optional) the position or pose of the subject
5. (optional) lighting description
6. (optional) camera position/framing
7. (optional) the visual style or medium ("photo", "illustration", "painting", and so on)

##Good Examples##
- Prompt: realistic editorial photo of female teacher standing at a blackboard with a warm smile
- Negative Prompt: crossed arms

- Prompt: whimsical and ethereal soft-shaded story illustration: A woman in a large hat stands at the ship's railing looking out across the ocean
- Negative Prompt: clouds, waves

- Prompt: drone view of a dark river winding through a stark Iceland landscape, cinematic quality

- Prompt: A cool looking stylish man in an orange jacket, dark skin, wearing reflective glasses. Shot from slightly low angle, face and chest in view, aqua blue sleek building shapes in background.

##Ouput instruction##
Users may input prompts in Chinese or English, but your final output should be a single English paragraph not exceeding 90 words.
Put the prompt in <prompt></prompt>, and if has negative prompt, then put in <negative_prompt></negative_prompt>

"""}]
        elif task=='image-to-video':
            system_instructions = [{"text":"""
You are a Prompt rewriting expert for image-to-video models, with expertise in film industry knowledge and skilled at helping users output final text prompts based on input initial frame images and potentially accompanying text prompts. 
The main goal is to help other models produce better video outputs based on these prompts and initial frame images. Users may input only images or both an image and text prompt, where the text could be in Chinese or English.
Your final output should be a single paragraph of English prompt not exceeding 90 words.

##You are proficient in the knowledge mentioned in:##
-You have a comprehensive understanding of the world, knowing various physical laws and can envision video content showing interactions between all things.
-You are imaginative and can envision the most perfect, visually impactful video scenes based on user-input images and prompts.
-You possess extensive film industry knowledge as a master director, capable of supplementing the best cinematographic language and visual effects based on user-input images and simple descriptions.


##Please follow these guidelines for rewriting prompts:##
-Subject: Based on user-uploaded image content, describe the video subject's characteristics in detail, emphasizing details while adjusting according to user's text prompt.
-Scene: Detailed description of video background, including location, environment, setting, season, time, etc., emphasizing details.
-Emotion and Atmosphere: Description of emotions and overall atmosphere conveyed in the video, referencing the image and user's prompt.
-Cinematography: Specify shot types, camera angles, and perspectives, Please refer to the guideline in DocumentPDFmessages.
-Visual Effects: Description of the visual style from user-uploaded images, such as Pixar animation, film style, realistic style, 3D animation, including descriptions of color schemes, lighting types, and contrast.
- Do not use any Amazon Bedrock filter words, such as human names.
                                    
##Good Examples##
- Prompt: "Cinematic dolly shot of a juicy cheeseburger with melting cheese, fries, and a condensation-covered cola on a worn diner table. Natural lighting, visible steam and droplets. 4k, photorealistic, shallow depth of field"
- Prompt: "Arc shot on a salad with dressing, olives and other vegetables; 4k; Cinematic;"
- Prompt: "First person view of a motorcycle riding through the forest road."
- Prompt: "Closeup of a large seashell in the sand. Gentle waves flow around the shell. Camera zoom in."
- Prompt: "Clothes hanging on a thread to dry, windy; sunny day; 4k; Cinematic; highest quality;"
- Prompt: "Slow cam of a man middle age; 4k; Cinematic; in a sunny day; peaceful; highest quality; dolly in;"
- Prompt: "A mushroom drinking a cup of coffee while sitting on a couch, photorealistic."

##Ouput instruction##
Users may input prompts in Chinese or English, but your final output should be a single English paragraph not exceeding 90 words.
Put your reponse in <prompt></prompt>
"""}]
        # Add user message
        messages = [
            {
                "role": "user",
                "content": [
                {"text": f"Please optimize:{description}"},
                ],
            }
        ]

        # Call Nova Pro with retry logic
        retry_count = 0
        while True:
            try:
                response = bedrock.converse(
                    modelId="amazon.nova-pro-v1:0",
                    messages=messages,
                    system=system_instructions,
                    inferenceConfig={
                        "temperature": 0.7,
                        "topP": 0.9,
                        "maxTokens": 500
                    }
                )
                break  # If successful, break out of retry loop
            except ClientError as e:
                if "Too many requests" in str(e) and retry_count < max_retries:
                    retry_count += 1
                    delay = initial_delay * (2 ** (retry_count - 1))  # Exponential backoff
                    logger.info(f"Rate limited. Retrying in {delay} seconds... (Attempt {retry_count}/{max_retries})")
                    time.sleep(delay)
                else:
                    raise  # Re-raise if max retries exceeded or different error
        
        # Extract the response
        output_message = response['output']['message']
        generated_prompt = ""
        negative_prompt = " "
        for content in output_message['content']:
            if 'text' in content:
                generated_prompt = parse(pattern = r"<prompt>(.*?)</prompt>",text=content['text'])
                print("generated_prompt:", generated_prompt)
                if task == "text-to-image":
                    negative_prompt = parse(pattern = r"<negative_prompt>(.*?)</negative_prompt>",text=content['text'])
                    print("negative_prompt:", negative_prompt)
                break
        if generated_prompt:
            logger.info(f"Generated enhanced prompt: {generated_prompt}")
            if negative_prompt == "":
                return generated_prompt," "
            else:
                return generated_prompt,negative_prompt
        else:
            logger.warning("No enhanced prompt generated, using original description")
            return description," "
            
    except ClientError as err:
        message = err.response["Error"]["Message"]
        logger.error(f"A client error occurred: {message}")
        return description, " "
    except Exception as e:
        logger.error(f"Error generating enhanced prompt: {str(e)}")
        return description, " "

if __name__ == "__main__":
    # Example usage
    test_description = "A peaceful garden with a small pond"
    task = "text-to-image"
    enhanced, negative = generate_enhanced_prompt(task, test_description)
    print(f"Original: {test_description}")
    print(f"Enhanced: {enhanced}")
    print(f"Negative prompt: {negative}")
