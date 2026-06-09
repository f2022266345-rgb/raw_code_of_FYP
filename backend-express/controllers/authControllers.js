import User from "../model/Users.js";

/**
 * Find or create a user in the database based on Clerk user details.
 * Also updates email/fullName if they have changed in Clerk.
 */
export const syncUserWithDatabase = async ({ clerkId, email, fullName }) => {
  if (!email) {
    throw new Error("Email address is required for provisioning");
  }

  // Check if user already exists in DB by Clerk ID
  let user = await User.findOne({ where: { clerkId } });

  if (user) {
    // Update existing user details if they changed
    let hasChanges = false;
    if (user.email !== email) {
      user.email = email;
      hasChanges = true;
    }
    if (user.fullName !== fullName) {
      user.fullName = fullName;
      hasChanges = true;
    }
    if (hasChanges) {
      await user.save();
      console.log(`User synced and updated in DB: ${user.id}`);
    }
  } else {
    // Create new user in DB
    user = await User.create({
      clerkId,
      email,
      fullName: fullName || email.split("@")[0],
    });
    console.log(`New user synced and created in DB: ${user.id}`);
  }

  return user;
};

export default {
  syncUserWithDatabase,
};
